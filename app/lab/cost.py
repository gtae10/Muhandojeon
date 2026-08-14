"""Lab 실행 비용 추정 — **돌리기 전에** 얼마 드는지 알려주는 계산기.

실수로 Lab 을 여러 번 돌리는 것이 예산 사고의 가장 흔한 경로다. 그래서 실행 API 와 CLI 는
이 추정을 먼저 보여주고 확인을 요구한다.

추정 근거는 두 가지다.
    history — 이전 실행의 `llm_usage` 기록(드라이런 포함)에서 세션당 평균 비용을 뽑아 스케일
    model   — 기록이 없을 때. 대표 프롬프트 하나를 실제로 만들어 토큰을 세고 호출 횟수를 곱한다

둘 다 캐시 미스를 가정한 상한이다. 캐시가 채워져 있으면 재실행 비용은 0 에 가깝다.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.llm import estimate_prompt_tokens, price_for, resolve
from app.models import LabSessionRow, LlmUsageRow

logger = logging.getLogger("app.lab.cost")

#: 용도별 출력 토큰 상한(호출부에서 실제로 쓰는 값과 맞춘다).
OUTPUT_LIMITS: dict[str, int] = {"clienteling": 400, "persona": 200, "judge": 400}


def _history_per_session() -> tuple[dict[str, float], int]:
    """가장 최근 실행의 세션당 용도별 비용. (per_purpose, 표본 세션 수)"""
    with session_scope() as db:
        latest_run = db.execute(
            select(LlmUsageRow.run_id)
            .where(LlmUsageRow.run_id.is_not(None))
            .order_by(LlmUsageRow.id.desc())
            .limit(1)
        ).scalar()
        if not latest_run:
            return {}, 0
        rows = (
            db.execute(select(LlmUsageRow).where(LlmUsageRow.run_id == latest_run)).scalars().all()
        )
        sessions = len(
            db.execute(select(LabSessionRow).where(LabSessionRow.run_id == latest_run))
            .scalars()
            .all()
        )
        per_purpose: dict[str, float] = {}
        for row in rows:
            if row.cached:  # 캐시 히트는 청구되지 않는다 → 상한 추정에서 제외
                continue
            per_purpose[str(row.purpose)] = per_purpose.get(str(row.purpose), 0.0) + float(
                row.cost_usd
            )
    if not sessions:
        return {}, 0
    return {k: v / sessions for k, v in per_purpose.items()}, sessions


def _model_per_session(max_turns: int) -> dict[str, float]:
    """대표 프롬프트로 토큰을 세어 세션당 비용을 만든다(기록이 없을 때)."""
    from app.adapters.clienteling import build_prompt
    from app.data.provider import get_provider
    from app.lab.judge import JUDGE_SYSTEM
    from app.lab.persona_bot import PERSONA_SYSTEM
    from app.strategies import get_strategy
    from contracts.clienteling import ClientelingReplyRequest
    from contracts.common import HesitationType

    provider = get_provider()
    products = provider.get_products()
    assets = provider.get_assets("CU-0001")
    if not products:
        return {}
    request = ClientelingReplyRequest(
        customer_id="CU-0001",
        hesitation_type=HesitationType.SIZE_UNCERTAIN,
        target_product=products[0],
        owned_assets=assets,
        strategy_id="S2",
    )
    clienteling_prompt = estimate_prompt_tokens(
        [dict(m) for m in build_prompt(request, get_strategy("S2"))]
    )
    # 페르소나·심판 프롬프트는 대화가 누적되므로 턴 수에 비례한다(보수적으로 잡는다).
    persona_prompt = estimate_prompt_tokens(
        [{"role": "system", "content": PERSONA_SYSTEM}, {"role": "user", "content": "x" * 800}]
    )
    judge_prompt = estimate_prompt_tokens(
        [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": "x" * 2000}]
    )

    out: dict[str, float] = {}
    for purpose, prompt_tokens, calls in (
        ("clienteling", clienteling_prompt, max_turns),
        ("persona", persona_prompt, max(0, max_turns - 1)),
        ("judge", judge_prompt, 1),
    ):
        price = price_for(resolve(purpose).model)
        out[purpose] = calls * price.cost_usd(prompt_tokens, OUTPUT_LIMITS.get(purpose, 400))
    return out


def estimate_lab_cost(total_sessions: int, max_turns: int) -> dict[str, Any]:
    """세션 수·턴 수로 실행 비용을 추정한다."""
    settings = get_settings()
    per_purpose, sample = _history_per_session()
    basis = "history"
    if not per_purpose:
        per_purpose = _model_per_session(max_turns)
        basis = "model"
        sample = 0

    per_session = sum(per_purpose.values())
    total = per_session * total_sessions
    return {
        "basis": basis,
        "sample_sessions": sample,
        "total_sessions": total_sessions,
        "max_turns": max_turns,
        "per_purpose_usd": {k: round(v * total_sessions, 5) for k, v in per_purpose.items()},
        "per_session_usd": round(per_session, 6),
        "per_session_krw": round(per_session * settings.usd_krw, 2),
        "total_usd": round(total, 5),
        "total_krw": round(total * settings.usd_krw, 1),
        "routing": {p: resolve(p).model for p in ("clienteling", "persona", "judge")},
        "note": (
            "캐시 미스를 가정한 상한이다. 캐시가 채워져 있으면 재실행 비용은 0 에 가깝다."
            if basis == "history"
            else "기록이 없어 대표 프롬프트 토큰으로 계산했다. 실제와 차이가 날 수 있다."
        ),
        "dry_run": settings.llm_dry_run,
        "llm_enabled": settings.llm_enabled,
    }
