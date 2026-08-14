"""드라이런 비용 추정 — Persona Bot Lab 을 실제로 돌리기 전에 반드시 통과하는 관문.

`LLM_DRY_RUN=true` 로 실행하면 **실제 호출 없이** 토큰 수와 예상 비용만 계산한다.
데모 시나리오 3종과 Lab 1회를 그대로 흘려보내므로 호출 횟수·프롬프트 크기가 실제와 같다.

    make estimate                          # 기본: 시나리오 3종 + Lab 1회(45세션)
    LLM_DRY_RUN=true python -m scripts.estimate_cost --runs 1
    LLM_DRY_RUN=true python -m scripts.estimate_cost --high-model gpt-4o --low-model gpt-4o-mini

출력에는 티어 분리 효과(모든 용도를 상위 모델로 돌렸을 때와의 차이)를 함께 넣는다.
페르소나 봇을 저가 티어로 내린 것이 얼마를 아끼는지 숫자로 보여야 판단할 수 있다.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db import init_db, session_scope
from app.demo import build_request, load_scenarios
from app.lab.runner import LabConfig, run_lab
from app.llm import get_budget, price_for, resolve, routing_report
from app.models import LlmUsageRow
from app.services.orchestrator import Orchestrator
from scripts.common import banner


def _max_usage_id() -> int:
    with session_scope() as db:
        return int(db.execute(select(LlmUsageRow.id).order_by(LlmUsageRow.id.desc())).scalar() or 0)


def _rows_after(marker: int) -> list[dict[str, Any]]:
    with session_scope() as db:
        rows = db.execute(select(LlmUsageRow).where(LlmUsageRow.id > marker)).scalars().all()
        return [
            {
                "purpose": str(r.purpose),
                "tier": str(r.tier),
                "model": str(r.model),
                "prompt_tokens": int(r.prompt_tokens),
                "completion_tokens": int(r.completion_tokens),
                "cost_usd": float(r.cost_usd),
                "dry_run": bool(r.dry_run),
                "cached": bool(r.cached),
            }
            for r in rows
        ]


def main() -> int:
    ap = argparse.ArgumentParser(description="드라이런 비용 추정")
    ap.add_argument("--runs", type=int, default=None, help="Lab 반복 횟수(기본 설정값)")
    ap.add_argument("--skip-lab", action="store_true", help="Lab 은 건너뛰고 시나리오만")
    ap.add_argument("--high-model", default=None, help="상위 티어 모델명(추정용 override)")
    ap.add_argument("--low-model", default=None, help="저가 티어 모델명(추정용 override)")
    args = ap.parse_args()

    if args.high_model:
        os.environ["LLM_MODEL"] = args.high_model
    if args.low_model:
        os.environ["LLM_MODEL_CHEAP"] = args.low_model

    banner("드라이런 비용 추정")
    settings = get_settings()
    init_db()

    if not settings.llm_dry_run:
        print("  ! LLM_DRY_RUN 이 false 다. 실제 호출이 발생한다 → `make estimate` 를 쓰라")
        return 1

    print("  용도별 라우팅")
    for row in routing_report():
        print(
            f"    {row['purpose']:<15} {row['tier']:<5} {row['model']:<22} "
            f"in ${row['input_per_1m_usd']}/1M out ${row['output_per_1m_usd']}/1M "
            f"({row['source']}, 단가표={row['pricing_entry']})"
        )

    marker = _max_usage_id()

    orchestrator = Orchestrator()
    scenarios = load_scenarios()
    for scenario in scenarios.values():
        orchestrator.advise(build_request(scenario))
    scenario_rows = _rows_after(marker)
    print(f"\n  데모 시나리오 {len(scenarios)}종 → LLM 호출 {len(scenario_rows)}건")

    lab_rows: list[dict[str, Any]] = []
    config = LabConfig.from_settings(runs_per_pair=args.runs)
    if not args.skip_lab:
        lab_marker = _max_usage_id()
        run_lab(config)
        lab_rows = _rows_after(lab_marker)
        print(f"  Persona Bot Lab {config.total_sessions}세션 → LLM 호출 {len(lab_rows)}건")

    def summarize(rows: list[dict[str, Any]], title: str) -> float:
        if not rows:
            print(f"\n  {title}: 호출 없음")
            return 0.0
        print(f"\n  {title}")
        print(
            f"    {'용도':<15} {'티어':<5} {'호출':>5} {'입력토큰':>9} {'출력토큰':>9} "
            f"{'예상비용':>11}"
        )
        total = 0.0
        for purpose in sorted({r["purpose"] for r in rows}):
            subset = [r for r in rows if r["purpose"] == purpose]
            cost = sum(r["cost_usd"] for r in subset)
            total += cost
            print(
                f"    {purpose:<15} {subset[0]['tier']:<5} {len(subset):>5} "
                f"{sum(r['prompt_tokens'] for r in subset):>9,} "
                f"{sum(r['completion_tokens'] for r in subset):>9,} "
                f"${cost:>10.4f}"
            )
        print(f"    {'합계':<15} {'':<5} {len(rows):>5} {'':>9} {'':>9} ${total:>10.4f}")
        return total

    scenario_cost = summarize(scenario_rows, f"데모 시나리오 {len(scenarios)}종 예상 비용")
    lab_cost = summarize(lab_rows, f"Persona Bot Lab 1회({config.total_sessions}세션) 예상 비용")

    # 티어 분리 효과: 같은 토큰 수를 전부 상위 모델로 돌렸다면?
    high_model = resolve("clienteling").model
    high_price = price_for(high_model)
    all_high = sum(
        high_price.cost_usd(r["prompt_tokens"], r["completion_tokens"]) for r in lab_rows
    )
    if lab_rows:
        saved = all_high - lab_cost
        ratio = (saved / all_high * 100) if all_high else 0.0
        print(
            f"\n  티어 분리 효과 (Lab 1회): ${lab_cost:.4f} vs 전부 상위({high_model}) "
            f"${all_high:.4f} → ${saved:.4f} 절감 ({ratio:.0f}%)"
        )

    state = get_budget().state(refresh=True)
    print(
        f"\n  예산: 누적 ${state.spent_usd:.4f} / 총 ${state.total_usd:.0f} "
        f"(경고 ${state.warn_usd:.0f} / 하드 ${state.hard_usd:.0f}) → 하드까지 "
        f"${state.remaining_to_hard:.2f}"
    )
    if lab_cost > 0:
        runs_left = int(state.remaining_to_hard / lab_cost)
        print(
            f"  남은 예산으로 가능한 Lab 실행: 약 {runs_left}회 "
            "(캐시 미스 기준. 캐시가 채워져 있으면 재실행 비용은 0 에 가깝다)"
        )
    krw = settings.usd_krw
    if lab_cost > 0 and config.total_sessions:
        per_session = lab_cost / config.total_sessions
        print(
            f"  상담 세션 1건당 원가: ${per_session:.5f} ≈ {per_session * krw:.1f}원 "
            f"(환율 {krw:,.0f}원/USD, 캐시 미스 기준)"
        )
    print(f"  시나리오 1회 재생 비용: ${scenario_cost:.4f} ≈ {scenario_cost * krw:.1f}원")
    print(
        "\n  주의: 드라이런은 출력 토큰을 max_tokens 상한으로 잡는 보수적 추정이다(실제는 더 적다)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
