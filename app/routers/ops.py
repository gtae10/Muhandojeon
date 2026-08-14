"""`/ops` — 예산·비용 운영 대시보드.

발표 자료가 되는 두 수치를 정확히 계산해서 보여주는 것이 목적이다.
    - 상담 세션 1건당 평균 원가(원화)
    - 남은 예산으로 가능한 Persona Bot Lab 잔여 실행 횟수

크레딧 총액 100달러, 초과 시 복구 수단이 없으므로 경고선(60)·하드 리밋(85)을 함께 표시한다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.llm import get_llm, load_capabilities, routing_report, usage_summary
from app.models import LabRunRow, LlmUsageRow

router = APIRouter(tags=["Ops"])

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def _lab_cost_history() -> list[dict[str, Any]]:
    """Lab 실행별 비용 — 잔여 실행 횟수 추정의 근거."""
    with session_scope() as db:
        runs = db.execute(select(LabRunRow).order_by(LabRunRow.started_at.desc())).scalars().all()
        run_rows = [
            {
                "run_id": r.run_id,
                "status": r.status,
                "sessions": r.completed_sessions,
                "started_at": r.started_at.isoformat() if r.started_at else None,
            }
            for r in runs
        ]
        usage = (
            db.execute(select(LlmUsageRow).where(LlmUsageRow.run_id.is_not(None))).scalars().all()
        )
        costs: dict[str, dict[str, Any]] = {}
        for row in usage:
            key = str(row.run_id)
            entry = costs.setdefault(
                key, {"billable_usd": 0.0, "saved_usd": 0.0, "calls": 0, "cached": 0}
            )
            entry["calls"] += 1
            if row.cached:
                entry["cached"] += 1
                entry["saved_usd"] += float(row.cost_usd)
            elif not row.dry_run:
                entry["billable_usd"] += float(row.cost_usd)

    out: list[dict[str, Any]] = []
    for run in run_rows:
        cost = costs.get(str(run["run_id"]), {})
        sessions = int(run["sessions"] or 0)
        billable = round(float(cost.get("billable_usd", 0.0)), 4)
        out.append(
            {
                **run,
                "llm_calls": cost.get("calls", 0),
                "cached_calls": cost.get("cached", 0),
                "billable_usd": billable,
                "saved_usd": round(float(cost.get("saved_usd", 0.0)), 4),
                "cost_per_session_usd": round(billable / sessions, 6) if sessions else 0.0,
            }
        )
    return out


@router.get("/ops", summary="예산·비용 대시보드", include_in_schema=False)
def ops_page() -> FileResponse:
    path = STATIC_DIR / "ops.html"
    if not path.exists():  # pragma: no cover
        raise HTTPException(status_code=500, detail="ops.html 이 없다")
    return FileResponse(path, media_type="text/html")


@router.get("/ops/summary", summary="예산 사용 요약 (게이지·용도별·캐시·세션 원가)")
def ops_summary() -> dict[str, Any]:
    settings = get_settings()
    summary = usage_summary(refresh=True)
    history = _lab_cost_history()

    # 잔여 Lab 실행 횟수: 실측 비용이 있으면 그걸 쓰고, 없으면 계산 불가로 표시한다.
    measured = [h for h in history if h["billable_usd"] > 0]
    last_cost = measured[0]["billable_usd"] if measured else 0.0
    remaining = summary["budget"]["remaining_to_hard_usd"]
    runs_left: int | None = int(remaining / last_cost) if last_cost > 0 else None

    return {
        **summary,
        "capabilities": load_capabilities(),
        "routing": routing_report(),
        "lab_runs": history,
        "lab_estimate": {
            "last_billable_usd": last_cost,
            "runs_left_with_remaining_budget": runs_left,
            "note": (
                "실측 비용이 있는 최근 실행 기준. 캐시가 채워져 있으면 재실행 비용은 0 에 가깝다."
                if last_cost > 0
                else "아직 과금된 Lab 실행이 없다. `make estimate` 로 드라이런 추정을 먼저 보라."
            ),
        },
        "cache": {
            "enabled": settings.llm_cache_enabled,
            "disk_entries": get_llm().cache_count(),
            "dir": str(settings.llm_cache_dir),
            "hit_rate": summary["totals"]["cache_hit_rate"],
            "saved_usd": summary["totals"]["saved_usd"],
        },
        "client_stats": get_llm().stats.as_dict(),
    }
