"""시뮬레이션 루프 — 5 페르소나 × 3 전략 × N회.

한 세션은 이렇게 흐른다.
    페르소나 봇(고객) ─┐
                      ├→ `POST /session/advise` 와 동일한 오케스트레이터 경로 (직원)
    소유 자산/컨디션 ─┘
    → 턴마다 고객이 반응하며 신뢰도가 갱신됨 → 최대 6턴 → 심판이 판정

오케스트레이터를 그대로 쓰는 이유: 인용 검증(5단계)을 포함한 실제 응답 경로를 측정해야
`owned_assets_used` 같은 지표가 데모와 일치한다.

결과는 SQLite(`lab_runs`, `lab_sessions`)에 저장하고 대화 전문도 보관한다.
**결과를 조작하지 않는다.** 심판과 페르소나 봇은 전략 id 를 보지 않는다.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.config import KST, get_settings
from app.db import session_scope
from app.lab.judge import Verdict, cited_in_transcript, llm_verdict, rule_verdict
from app.lab.persona_bot import (
    TRUST_START,
    MessageFeatures,
    clamp_trust,
    customer_reply,
    evaluate_turn,
    extract_features,
    llm_customer_reply,
)
from app.llm import get_llm
from app.models import LabRunRow, LabSessionRow
from app.personas import Persona, load_personas, validate_bindings
from app.services.orchestrator import Orchestrator
from app.store import get_store
from app.strategies import load_strategies
from contracts.common import ChatTurn, Role
from contracts.orchestrator import AdviseRequest, AdviseResponse

logger = logging.getLogger("app.lab")

#: 반복 회차별 초기 신뢰도 오프셋. 결정적 시스템에서 같은 조건 N회는 의미가 없으므로
#: 회차마다 고객의 초기 태도(오프닝 + 신뢰도)를 다르게 준다.
ITERATION_TRUST_OFFSETS: tuple[float, ...] = (0.0, -0.3, 0.3)

_progress_lock = threading.Lock()
PROGRESS: dict[str, dict[str, Any]] = {}


@dataclass
class LabConfig:
    """실행 설정."""

    runs_per_pair: int
    max_turns: int
    concurrency: int
    persona_ids: list[str] = field(default_factory=list)
    strategy_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_settings(cls, **overrides: Any) -> LabConfig:
        settings = get_settings()
        config = cls(
            runs_per_pair=settings.lab_runs_per_pair,
            max_turns=settings.lab_max_turns,
            concurrency=settings.lab_max_concurrency,
            persona_ids=sorted(load_personas()),
            strategy_ids=sorted(load_strategies()),
        )
        for key, value in overrides.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)
        return config

    @property
    def total_sessions(self) -> int:
        return len(self.persona_ids) * len(self.strategy_ids) * self.runs_per_pair

    def as_dict(self) -> dict[str, Any]:
        return {
            "runs_per_pair": self.runs_per_pair,
            "max_turns": self.max_turns,
            "concurrency": self.concurrency,
            "personas": self.persona_ids,
            "strategies": self.strategy_ids,
            "total_sessions": self.total_sessions,
            "llm_enabled": get_settings().llm_enabled,
        }


@dataclass
class SessionResult:
    """세션 1건의 결과."""

    persona_id: str
    strategy_id: str
    iteration: int
    customer_id: str
    target_product_id: str
    hesitation_type: str
    verdict: Verdict
    transcript: list[dict[str, str]]
    cited_asset_ids: list[str]
    owned_assets_used: bool
    degraded: bool
    trust_history: list[float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "persona_id": self.persona_id,
            "strategy_id": self.strategy_id,
            "iteration": self.iteration,
            "customer_id": self.customer_id,
            "target_product_id": self.target_product_id,
            "hesitation_type": self.hesitation_type,
            "owned_assets_used": self.owned_assets_used,
            "cited_asset_ids": self.cited_asset_ids,
            "degraded": self.degraded,
            "trust_history": self.trust_history,
            **self.verdict.as_dict(),
        }


def _session_events(persona: Persona, iteration: int) -> list[Any]:
    """페르소나의 초기 망설임과 같은 라벨을 가진 **실제 세션**의 이벤트를 쓴다."""
    store = get_store()
    candidates = sorted(
        store.sessions_by_label(persona.initial_hesitation.value), key=lambda s: s.session_id
    )
    if not candidates:
        return []
    chosen = candidates[iteration % len(candidates)]
    return list(chosen.events)


def simulate_session(
    persona: Persona,
    strategy_id: str,
    iteration: int,
    max_turns: int,
    run_id: str | None = None,
) -> SessionResult:
    """한 세션(최대 max_turns 턴)을 끝까지 돌리고 판정까지 낸다."""
    llm = get_llm()
    orchestrator = Orchestrator()
    events = _session_events(persona, iteration)

    trust = clamp_trust(
        TRUST_START + ITERATION_TRUST_OFFSETS[iteration % len(ITERATION_TRUST_OFFSETS)]
    )
    trust_history: list[float] = [trust]
    history: list[ChatTurn] = [ChatTurn(role=Role.CUSTOMER, content=persona.opening(iteration))]
    transcript: list[dict[str, str]] = [{"role": "customer", "content": persona.opening(iteration)}]

    unmet = list(persona.needs)
    met_so_far: set[str] = set()
    evidence_seen = False
    pressure_seen = False
    cta_seen = False
    cited_any: list[str] = []
    degraded = False
    owned_used = False
    hesitation = persona.initial_hesitation.value
    turns_used = 0
    feats: MessageFeatures | None = None

    for turn in range(1, max_turns + 1):
        turns_used = turn
        response: AdviseResponse = orchestrator.advise(
            AdviseRequest(
                customer_id=persona.customer_id,
                target_product_id=persona.target_product_id,
                session_events=events,
                strategy_id=strategy_id,
                history=history,
                scenario_id=f"lab-{persona.id}-{strategy_id}-{iteration}",
            )
        )
        degraded = degraded or response.degraded
        owned_used = owned_used or response.owned_assets_used
        hesitation = response.hesitation_type.value
        for asset_id in response.cited_asset_ids:
            if asset_id not in cited_any:
                cited_any.append(asset_id)

        # 인용 검증을 통과한 값으로 특징을 뽑는다(제거된 환각 인용은 근거로 세지 않는다).
        feats = extract_features(_as_reply(response))
        pressure_seen = pressure_seen or feats.pressure
        cta_seen = cta_seen or (feats.cta.value != "NONE")

        evaluation = evaluate_turn(
            persona, feats, already_met=met_so_far, evidence_seen=evidence_seen
        )
        evidence_seen = evidence_seen or (feats.cites_asset and feats.condition_evidence)
        met_so_far |= evaluation.met
        trust = clamp_trust(trust + evaluation.delta)
        trust_history.append(trust)
        unmet = [n for n in unmet if n not in evaluation.met]

        transcript.append(
            {
                "role": "advisor",
                "content": response.message,
                "cta": response.cta.value,
                "cited": ",".join(response.cited_asset_ids),
                "trust_after": f"{trust:.2f}",
                "trust_reasons": " | ".join(evaluation.reasons),
            }
        )
        history.append(ChatTurn(role=Role.ADVISOR, content=response.message))

        decided = trust >= persona.trust_threshold and cta_seen
        gave_up = trust <= 1.5
        if decided or gave_up or turn == max_turns:
            reply = customer_reply(persona, feats, trust, turn, unmet)
            transcript.append({"role": "customer", "content": reply})
            break

        reply = llm_customer_reply(
            llm,
            persona,
            response.message,
            [(t["role"], t["content"]) for t in transcript],
            trust,
            unmet,
            run_id=run_id,
        ) or customer_reply(persona, feats, trust, turn, unmet)
        transcript.append({"role": "customer", "content": reply})
        history.append(ChatTurn(role=Role.CUSTOMER, content=reply))

    base = rule_verdict(
        persona=persona,
        trust=trust,
        turns=turns_used,
        unmet=unmet,
        pressure_seen=pressure_seen,
        cta_seen=cta_seen,
        cited_any=bool(cited_any),
    )
    verdict = llm_verdict(llm, persona, transcript, base, run_id=run_id)

    return SessionResult(
        persona_id=persona.id,
        strategy_id=strategy_id,
        iteration=iteration,
        customer_id=persona.customer_id,
        target_product_id=persona.target_product_id,
        hesitation_type=hesitation,
        verdict=verdict,
        transcript=transcript,
        cited_asset_ids=cited_any or cited_in_transcript(transcript),
        owned_assets_used=owned_used,
        degraded=degraded,
        trust_history=trust_history,
    )


def _as_reply(response: AdviseResponse) -> Any:
    """오케스트레이터 응답을 상담 응답 계약 형태로 감싼다(특징 추출 재사용)."""
    from contracts.clienteling import ClientelingReplyResponse

    return ClientelingReplyResponse(
        message=response.message,
        cited_asset_ids=list(response.cited_asset_ids),
        cta=response.cta,
        reasoning=response.reasoning,
    )


def new_run_id() -> str:
    return f"run-{datetime.now(tz=KST).strftime('%Y%m%d-%H%M%S')}"


def _set_progress(run_id: str, **fields: Any) -> None:
    with _progress_lock:
        current = PROGRESS.setdefault(run_id, {})
        current.update(fields)


def get_progress(run_id: str) -> dict[str, Any]:
    with _progress_lock:
        return dict(PROGRESS.get(run_id, {}))


def run_lab(config: LabConfig | None = None, run_id: str | None = None) -> str:
    """시뮬레이션 전체 실행. run_id 를 반환한다(진행률은 `get_progress`)."""
    settings = get_settings()
    config = config or LabConfig.from_settings()
    run_id = run_id or new_run_id()
    personas = load_personas()
    problems = validate_bindings()
    if problems:
        logger.warning("페르소나 바인딩 문제: %s", problems)

    started = datetime.now(tz=KST)
    with session_scope() as db:
        db.merge(
            LabRunRow(
                run_id=run_id,
                started_at=started,
                config={**config.as_dict(), "binding_problems": problems},
                total_sessions=config.total_sessions,
                completed_sessions=0,
                status="running",
            )
        )
    _set_progress(
        run_id,
        status="running",
        total=config.total_sessions,
        completed=0,
        converted=0,
        started_at=started.isoformat(),
        llm_enabled=settings.llm_enabled,
        binding_problems=problems,
        recent=[],
    )

    jobs: list[tuple[Persona, str, int]] = [
        (personas[pid], sid, i)
        for pid in config.persona_ids
        if pid in personas
        for sid in config.strategy_ids
        for i in range(config.runs_per_pair)
    ]

    completed = 0
    converted = 0
    with ThreadPoolExecutor(max_workers=max(1, config.concurrency)) as pool:
        futures = {
            pool.submit(simulate_session, persona, sid, i, config.max_turns, run_id): (
                persona,
                sid,
                i,
            )
            for persona, sid, i in jobs
        }
        for future in as_completed(futures):
            persona, sid, i = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # pragma: no cover - 개별 세션 실패는 전체를 막지 않는다
                logger.exception("세션 실패 %s/%s/%d: %s", persona.id, sid, i, exc)
                completed += 1
                _set_progress(run_id, completed=completed)
                continue

            completed += 1
            converted += int(result.verdict.converted)
            with session_scope() as db:
                db.add(
                    LabSessionRow(
                        run_id=run_id,
                        persona_id=result.persona_id,
                        strategy_id=result.strategy_id,
                        iteration=result.iteration,
                        customer_id=result.customer_id,
                        target_product_id=result.target_product_id,
                        hesitation_type=result.hesitation_type,
                        converted=result.verdict.converted,
                        turns_to_decision=result.verdict.turns_to_decision,
                        drop_reason=result.verdict.drop_reason,
                        trust_score=result.verdict.trust_score,
                        judge_reasoning=f"[{result.verdict.source}] {result.verdict.reasoning}",
                        cited_asset_ids=result.cited_asset_ids,
                        owned_assets_used=result.owned_assets_used,
                        transcript=result.transcript,
                        degraded=result.degraded,
                        created_at=datetime.now(tz=KST),
                    )
                )
            recent = get_progress(run_id).get("recent", [])
            recent = ([*recent, result.as_dict()])[-8:]
            _set_progress(run_id, completed=completed, converted=converted, recent=recent)

    finished = datetime.now(tz=KST)
    with session_scope() as db:
        row = db.get(LabRunRow, run_id)
        if row is not None:
            row.finished_at = finished
            row.completed_sessions = completed
            row.status = "done"
    _set_progress(run_id, status="done", completed=completed, finished_at=finished.isoformat())
    logger.info(
        "Lab 완료 %s — %d/%d 세션, 전환 %d건 (%.1f초)",
        run_id,
        completed,
        config.total_sessions,
        converted,
        (finished - started).total_seconds(),
    )
    return run_id
