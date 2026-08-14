"""예산 가드 — 크레딧 100달러를 넘기지 않게 하는 장치.

3단 구조다.
    LLM_BUDGET_TOTAL_USD=100   총액(표시용 기준)
    LLM_BUDGET_WARN_USD=60     초과 시 로그 경고 + /ops 배너
    LLM_BUDGET_HARD_USD=85     초과 시 **새 호출 전면 거부, 캐시만 반환**

하드 리밋을 100 이 아니라 85 로 두는 이유: 발표 당일 예상 못 한 재실행 여유분 15달러를
남겨두는 것이다. 100 으로 잡으면 당일 아침에 크레딧이 0 인 상태를 만들 수 있다.

**사후 집계로는 늦다.** 호출 전에 입력 토큰을 추정해 예상 비용을 계산하고, 하드 리밋을 넘길
호출은 실행하지 않는다(`check_before_call`). 실제 사용량은 응답의 `usage` 로 기록을 덮어쓴다.

모든 호출은 `llm_usage` 테이블에 기록된다(용도·모델·토큰·비용·지연·캐시히트·드라이런).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

from app.config import KST, Settings, get_settings
from app.db import session_scope
from app.llm.pricing import price_for
from app.models import LlmUsageRow

logger = logging.getLogger("app.llm.budget")


class BudgetExceeded(RuntimeError):
    """하드 리밋 초과. 호출을 실행하지 않았다는 뜻이다(캐시 폴백으로 처리한다)."""


@dataclass(frozen=True)
class UsageRecord:
    """집계용 사용량 행(DB 세션 밖으로 값만 꺼낸 것)."""

    purpose: str
    tier: str
    model: str
    cost_usd: float
    cached: bool
    dry_run: bool
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    run_id: str | None

    @property
    def billable(self) -> bool:
        return not self.cached and not self.dry_run


@dataclass
class BudgetState:
    """현재 예산 상태."""

    spent_usd: float
    total_usd: float
    warn_usd: float
    hard_usd: float

    @property
    def remaining_to_hard(self) -> float:
        return max(0.0, self.hard_usd - self.spent_usd)

    @property
    def remaining_to_total(self) -> float:
        return max(0.0, self.total_usd - self.spent_usd)

    @property
    def level(self) -> str:
        if self.spent_usd >= self.hard_usd:
            return "hard"
        if self.spent_usd >= self.warn_usd:
            return "warn"
        return "ok"

    @property
    def usage_ratio(self) -> float:
        return round(self.spent_usd / self.total_usd, 4) if self.total_usd else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "spent_usd": round(self.spent_usd, 4),
            "total_usd": self.total_usd,
            "warn_usd": self.warn_usd,
            "hard_usd": self.hard_usd,
            "remaining_to_hard_usd": round(self.remaining_to_hard, 4),
            "remaining_to_total_usd": round(self.remaining_to_total, 4),
            "usage_ratio": self.usage_ratio,
            "level": self.level,
        }


class BudgetGuard:
    """누적 사용액을 들고 호출 전 게이트를 수행한다."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spent: float | None = None

    # ── 누적액 ────────────────────────────────────────────────
    def _load_spent(self) -> float:
        """실제 청구되는 행(캐시 히트·드라이런 제외)의 비용 합계."""
        try:
            with session_scope() as db:
                total = db.execute(
                    select(func.coalesce(func.sum(LlmUsageRow.cost_usd), 0.0)).where(
                        LlmUsageRow.cached.is_(False), LlmUsageRow.dry_run.is_(False)
                    )
                ).scalar()
                return float(total or 0.0)
        except Exception as exc:  # noqa: BLE001 - DB 미생성 등에서도 서버는 떠야 한다
            logger.warning("누적 사용액 조회 실패(0 으로 간주): %s", exc)
            return 0.0

    def spent_usd(self, refresh: bool = False) -> float:
        with self._lock:
            if refresh or self._spent is None:
                self._spent = self._load_spent()
            return self._spent

    def state(self, refresh: bool = False, settings: Settings | None = None) -> BudgetState:
        """예산 상태.

        `settings` 를 받는 이유: 호출 주체(클라이언트)의 설정을 따라야 한다. 전역 설정만 읽으면
        테스트나 다중 설정 환경에서 리밋이 무시된다.
        """
        settings = settings or get_settings()
        return BudgetState(
            spent_usd=self.spent_usd(refresh=refresh),
            total_usd=settings.llm_budget_total_usd,
            warn_usd=settings.llm_budget_warn_usd,
            hard_usd=settings.llm_budget_hard_usd,
        )

    def invalidate(self) -> None:
        with self._lock:
            self._spent = None

    # ── 게이트 ────────────────────────────────────────────────
    def check_before_call(
        self,
        purpose: str,
        model: str,
        estimated_cost_usd: float,
        settings: Settings | None = None,
    ) -> None:
        """예상 비용을 더해 하드 리밋을 넘기면 `BudgetExceeded`. 경고선은 로그만 남긴다."""
        state = self.state(settings=settings)
        projected = state.spent_usd + estimated_cost_usd
        if projected > state.hard_usd:
            logger.error(
                "예산 하드 리밋 초과 예상 → 호출 거부 "
                "(purpose=%s model=%s 누적 $%.2f + 예상 $%.4f > 하드 $%.2f)",
                purpose,
                model,
                state.spent_usd,
                estimated_cost_usd,
                state.hard_usd,
            )
            raise BudgetExceeded(
                f"하드 리밋 ${state.hard_usd:.2f} 초과 예상 "
                f"(누적 ${state.spent_usd:.2f} + 예상 ${estimated_cost_usd:.4f}). "
                "캐시만 반환한다."
            )
        if projected > state.warn_usd:
            logger.warning(
                "예산 경고선 초과 (누적 $%.2f / 경고 $%.2f / 하드 $%.2f) purpose=%s",
                state.spent_usd,
                state.warn_usd,
                state.hard_usd,
                purpose,
            )

    # ── 기록 ─────────────────────────────────────────────────
    def record(
        self,
        *,
        purpose: str,
        tier: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        estimated: bool,
        cached: bool,
        dry_run: bool,
        latency_ms: float,
        cache_key: str = "",
        run_id: str | None = None,
        note: str = "",
    ) -> float:
        """호출 1건을 기록하고 비용을 반환한다.

        `cached=True` 인 행의 비용은 실제 청구액이 아니라 **아꼈을 금액**이다(절감액 계산용).
        """
        price = price_for(model)
        cost = price.cost_usd(prompt_tokens, completion_tokens)
        row = LlmUsageRow(
            created_at=datetime.now(tz=KST),
            purpose=purpose,
            tier=tier,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            estimated=estimated,
            cached=cached,
            dry_run=dry_run,
            latency_ms=round(latency_ms, 2),
            cache_key=cache_key[:40],
            run_id=run_id,
            note=(note or f"pricing={price.source}")[:200],
        )
        try:
            with session_scope() as db:
                db.add(row)
        except Exception as exc:  # noqa: BLE001 - 기록 실패가 데모를 막지 않게 한다
            logger.warning("사용량 기록 실패: %s", exc)
            return cost
        if not cached and not dry_run:
            with self._lock:
                if self._spent is None:
                    self._spent = self._load_spent()
                else:
                    self._spent += cost
        return cost


_guard: BudgetGuard | None = None


def get_budget() -> BudgetGuard:
    """프로세스 전역 예산 가드."""
    global _guard
    if _guard is None:
        _guard = BudgetGuard()
    return _guard


def usage_summary(refresh: bool = True) -> dict[str, Any]:
    """`/ops` 대시보드용 집계 — 용도별 비용, 캐시 히트율, 세션 원가, Lab 잔여 횟수."""
    settings = get_settings()
    guard = get_budget()
    state = guard.state(refresh=refresh)

    by_purpose: list[dict[str, Any]] = []
    records: list[UsageRecord] = []
    try:
        with session_scope() as db:
            rows = db.execute(select(LlmUsageRow)).scalars().all()
            records = [
                UsageRecord(
                    purpose=str(r.purpose),
                    tier=str(r.tier),
                    model=str(r.model),
                    cost_usd=float(r.cost_usd),
                    cached=bool(r.cached),
                    dry_run=bool(r.dry_run),
                    prompt_tokens=int(r.prompt_tokens),
                    completion_tokens=int(r.completion_tokens),
                    latency_ms=float(r.latency_ms),
                    run_id=r.run_id,
                )
                for r in rows
            ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("사용량 집계 실패: %s", exc)
        records = []

    for purpose in sorted({r.purpose for r in records}):
        subset = [r for r in records if r.purpose == purpose]
        billable = [r for r in subset if r.billable]
        cached = [r for r in subset if r.cached]
        by_purpose.append(
            {
                "purpose": purpose,
                "tier": subset[0].tier if subset else "",
                "model": subset[-1].model if subset else "",
                "calls": len(subset),
                "billable_calls": len(billable),
                "cached_calls": len(cached),
                "cost_usd": round(sum(r.cost_usd for r in billable), 4),
                "saved_usd": round(sum(r.cost_usd for r in cached), 4),
                "prompt_tokens": sum(r.prompt_tokens for r in billable),
                "completion_tokens": sum(r.completion_tokens for r in billable),
                "avg_latency_ms": round(sum(r.latency_ms for r in billable) / len(billable), 1)
                if billable
                else 0.0,
            }
        )

    billable_calls = sum(1 for r in records if r.billable)
    cached_calls = sum(1 for r in records if r.cached)
    totals = {
        "calls": len(records),
        "billable_calls": billable_calls,
        "cached_calls": cached_calls,
        "dry_run_calls": sum(1 for r in records if r.dry_run),
        "prompt_tokens": sum(r.prompt_tokens for r in records),
        "completion_tokens": sum(r.completion_tokens for r in records),
        "saved_usd": round(sum(r.cost_usd for r in records if r.cached), 4),
    }
    lookups = billable_calls + cached_calls
    hit_rate = round(cached_calls / lookups, 4) if lookups else 0.0

    # 상담 세션 1건당 원가: Lab 세션 수로 나눈다(발표 슬라이드용 수치).
    lab_sessions = 0
    try:
        with session_scope() as db:
            from app.models import LabSessionRow

            lab_sessions = int(
                db.execute(select(func.count()).select_from(LabSessionRow)).scalar() or 0
            )
    except Exception:  # noqa: BLE001
        lab_sessions = 0

    cost_per_session_usd = round(state.spent_usd / lab_sessions, 6) if lab_sessions else 0.0
    return {
        "budget": state.as_dict(),
        "by_purpose": by_purpose,
        "totals": {**totals, "cache_hit_rate": hit_rate},
        "per_session": {
            "lab_sessions_recorded": lab_sessions,
            "cost_per_session_usd": cost_per_session_usd,
            "cost_per_session_krw": round(cost_per_session_usd * settings.usd_krw, 2),
            "usd_krw": settings.usd_krw,
        },
        "dry_run": settings.llm_dry_run,
        "cache_enabled": settings.llm_cache_enabled,
        "llm_enabled": settings.llm_enabled,
    }
