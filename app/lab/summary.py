"""Lab 결과 집계 — 대시보드와 CLI 가 공유한다.

전략별 전환율, 페르소나 × 전략 히트맵, 이탈 사유 분포를 **실측값 그대로** 계산한다.
S2 가 지면 그 사실이 그대로 나와야 한다(원인 분석이 이 Lab 의 목적이다).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.models import LabRunRow, LabSessionRow
from app.personas import load_personas
from app.strategies import load_strategies


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    with session_scope() as db:
        rows = (
            db.execute(select(LabRunRow).order_by(LabRunRow.started_at.desc()).limit(limit))
            .scalars()
            .all()
        )
        return [
            {
                "run_id": r.run_id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "status": r.status,
                "total_sessions": r.total_sessions,
                "completed_sessions": r.completed_sessions,
                "config": r.config,
            }
            for r in rows
        ]


def latest_run_id() -> str | None:
    runs = list_runs(limit=1)
    return runs[0]["run_id"] if runs else None


def _rate(converted: int, total: int) -> float:
    return round(converted / total, 4) if total else 0.0


def summarize(run_id: str) -> dict[str, Any]:
    """전략별/페르소나별 집계. 세션이 없으면 빈 구조를 돌려준다."""
    strategies = load_strategies()
    personas = load_personas()
    with session_scope() as db:
        run = db.get(LabRunRow, run_id)
        sessions = (
            db.execute(select(LabSessionRow).where(LabSessionRow.run_id == run_id)).scalars().all()
        )
        rows: list[dict[str, Any]] = [
            {
                "id": s.id,
                "persona_id": s.persona_id,
                "strategy_id": s.strategy_id,
                "iteration": s.iteration,
                "customer_id": s.customer_id,
                "target_product_id": s.target_product_id,
                "hesitation_type": s.hesitation_type,
                "converted": s.converted,
                "turns_to_decision": s.turns_to_decision,
                "drop_reason": s.drop_reason,
                "trust_score": s.trust_score,
                "judge_reasoning": s.judge_reasoning,
                "cited_asset_ids": s.cited_asset_ids,
                "owned_assets_used": s.owned_assets_used,
                "degraded": s.degraded,
            }
            for s in sessions
        ]
        run_info = (
            {
                "run_id": run.run_id,
                "status": run.status,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "config": run.config,
                "total_sessions": run.total_sessions,
                "completed_sessions": run.completed_sessions,
            }
            if run
            else {}
        )

    by_strategy: dict[str, dict[str, Any]] = {}
    for sid in sorted(strategies):
        subset = [r for r in rows if r["strategy_id"] == sid]
        converted = [r for r in subset if r["converted"]]
        by_strategy[sid] = {
            "strategy_id": sid,
            "name": strategies[sid].name,
            "cite_assets": strategies[sid].cite_assets,
            "sessions": len(subset),
            "converted": len(converted),
            "conversion_rate": _rate(len(converted), len(subset)),
            "avg_turns_to_decision": round(
                sum(r["turns_to_decision"] for r in subset) / len(subset), 2
            )
            if subset
            else 0.0,
            "avg_trust": round(sum(r["trust_score"] for r in subset) / len(subset), 2)
            if subset
            else 0.0,
            "asset_citation_rate": _rate(
                sum(1 for r in subset if r["owned_assets_used"]), len(subset)
            ),
            "degraded_sessions": sum(1 for r in subset if r["degraded"]),
        }

    heatmap: list[dict[str, Any]] = []
    for pid in sorted(personas):
        row: dict[str, Any] = {
            "persona_id": pid,
            "persona_name": personas[pid].name,
            "customer_id": personas[pid].customer_id,
            "cells": {},
        }
        for sid in sorted(strategies):
            subset = [r for r in rows if r["persona_id"] == pid and r["strategy_id"] == sid]
            row["cells"][sid] = {
                "sessions": len(subset),
                "converted": sum(1 for r in subset if r["converted"]),
                "conversion_rate": _rate(sum(1 for r in subset if r["converted"]), len(subset)),
                "avg_trust": round(sum(r["trust_score"] for r in subset) / len(subset), 2)
                if subset
                else 0.0,
            }
        heatmap.append(row)

    drop_counter: Counter[str] = Counter()
    drop_by_strategy: dict[str, Counter[str]] = defaultdict(Counter)
    for r in rows:
        if r["converted"]:
            continue
        reason = r["drop_reason"] or "UNKNOWN"
        drop_counter[reason] += 1
        drop_by_strategy[r["strategy_id"]][reason] += 1

    judge_sources = Counter(
        (r["judge_reasoning"] or "").split("]")[0].lstrip("[") for r in rows if r["judge_reasoning"]
    )

    return {
        "run": run_info,
        "totals": {
            "sessions": len(rows),
            "converted": sum(1 for r in rows if r["converted"]),
            "conversion_rate": _rate(sum(1 for r in rows if r["converted"]), len(rows)),
            "degraded": sum(1 for r in rows if r["degraded"]),
        },
        "by_strategy": list(by_strategy.values()),
        "heatmap": heatmap,
        "drop_reasons": [{"reason": k, "count": v} for k, v in drop_counter.most_common()],
        "drop_reasons_by_strategy": {
            sid: [{"reason": k, "count": v} for k, v in counter.most_common()]
            for sid, counter in drop_by_strategy.items()
        },
        "sessions": rows,
        "simulation_mode": {
            "llm_enabled": get_settings().llm_enabled,
            "judge_sources": dict(judge_sources),
            "caveat": (
                "LLM 미연결 → 페르소나 봇과 심판이 규칙 모델이다. 규칙 모델은 "
                "'고객이 자기 물건에 대한 근거를 중시한다'(evidence_need)를 파라미터로 갖고 "
                "있고, "
                "그 근거를 제공하는 전략은 S2 뿐이다. 따라서 S2 우세는 상당 부분 가정의 "
                "결과이며 언어적 설득력의 증거가 아니다(순환). 이 모드에서 유효한 산출물은 "
                "하네스 완주 여부, "
                "이탈 사유 분포, 그리고 LLM 연결 시 같은 하네스로 실측할 수 있다는 점이다. "
                "반복 회차는 초기 신뢰도 ±0.3 과 오프닝 변형만 다르므로 셀 값이 0%/100% 로 몰린다."
            )
            if not get_settings().llm_enabled
            else (
                "LLM 연결 상태. 페르소나 발화와 판정에 LLM 이 사용되며, "
                "temperature 0 + 시드 고정으로 재현성을 유지한다."
            ),
        },
    }


def session_detail(session_id: int) -> dict[str, Any] | None:
    """대화 전문 포함 상세."""
    with session_scope() as db:
        row = db.get(LabSessionRow, session_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "run_id": row.run_id,
            "persona_id": row.persona_id,
            "strategy_id": row.strategy_id,
            "iteration": row.iteration,
            "customer_id": row.customer_id,
            "target_product_id": row.target_product_id,
            "hesitation_type": row.hesitation_type,
            "converted": row.converted,
            "turns_to_decision": row.turns_to_decision,
            "drop_reason": row.drop_reason,
            "trust_score": row.trust_score,
            "judge_reasoning": row.judge_reasoning,
            "cited_asset_ids": row.cited_asset_ids,
            "owned_assets_used": row.owned_assets_used,
            "degraded": row.degraded,
            "transcript": row.transcript,
        }
