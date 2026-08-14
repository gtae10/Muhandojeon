"""헬스 엔드포인트 — 발표 직전 5초 점검용.

`/health/detail` 하나로 다음을 확인한다.
    - 어댑터별 모드(mock/http)와 최근 응답 상태·지연
    - 데이터 소스(external/synth)와 적재량
    - LLM 연결 여부, 디스크 캐시 적재 건수
    - 데모 모드, 시나리오 수
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.adapters.registry import adapter_report
from app.config import get_settings
from app.llm import get_llm
from app.store import get_store

router = APIRouter(tags=["Health"])


@router.get("/health", summary="가벼운 생존 확인")
def health() -> dict[str, Any]:
    store = get_store()
    return {
        "status": "ok" if store.ready else "degraded",
        "adapter_mode": get_settings().adapter_mode,
        "demo_mode": get_settings().demo_mode,
    }


@router.get("/health/detail", summary="발표 직전 전체 상태 점검")
def health_detail() -> dict[str, Any]:
    settings = get_settings()
    store = get_store()
    llm = get_llm()

    db_counts: dict[str, int | str] = {}
    try:
        from sqlalchemy import func, select

        from app.db import session_scope
        from app.models import LabRunRow, LabSessionRow, LlmUsageRow

        with session_scope() as db:
            for name, model in (
                ("lab_runs", LabRunRow),
                ("lab_sessions", LabSessionRow),
                ("llm_usage", LlmUsageRow),
            ):
                counted = db.execute(select(func.count()).select_from(model)).scalar()
                db_counts[name] = int(counted or 0)
    except Exception as exc:  # pragma: no cover - DB 미생성
        db_counts["error"] = str(exc)[:200]

    scenarios: int | str
    try:
        from app.demo import load_scenarios

        scenarios = len(load_scenarios())
    except Exception as exc:  # pragma: no cover
        scenarios = f"error: {exc}"[:120]

    store_stats = store.stats()
    return {
        "status": "ok" if store.ready else "degraded",
        "adapters": adapter_report(),
        "data": {
            "seed_source": store_stats["seed_source"],
            "seed_source_setting": settings.seed_source,
            "label_mismatch": store_stats["label_mismatch"],
            "products": store_stats["products"],
            "customers": store_stats["customers"],
            "assets": store_stats["assets"],
            "sessions": store_stats["sessions"],
            "load_errors": store_stats["load_errors"],
        },
        "db": db_counts,
        "llm": {
            "enabled": settings.llm_enabled,
            "model": settings.llm_model if settings.llm_enabled else None,
            "judge_model": settings.judge_model if settings.llm_enabled else None,
            "base_url": settings.llm_base_url if settings.llm_enabled else None,
            "cache_entries": llm.cache_count(),
            **llm.stats.as_dict(),
        },
        "demo": {
            "demo_mode": settings.demo_mode,
            "scenarios": scenarios,
            "upstream_timeout_seconds": settings.upstream_timeout_seconds,
            "upstream_retries": settings.upstream_retries,
        },
        "lab": {
            "concurrency": settings.lab_concurrency,
            "runs_per_pair": settings.lab_runs_per_pair,
            "max_turns": settings.lab_max_turns,
        },
    }
