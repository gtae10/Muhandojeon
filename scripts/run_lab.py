"""Persona Bot Lab CLI — 5 페르소나 × 3 전략 × N회 시뮬레이션.

    python -m scripts.run_lab                     # 기본 45세션
    python -m scripts.run_lab --runs 1            # 15세션 (빠른 확인)
    python -m scripts.run_lab --concurrency 8
    python -m scripts.run_lab --summary-only      # 최근 실행 결과만 출력

결과는 SQLite 에 저장되고 `/lab` 대시보드에서 그대로 보인다.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from app.config import get_settings
from app.db import init_db
from app.lab.runner import LabConfig, run_lab
from app.lab.summary import latest_run_id, summarize
from app.personas import validate_bindings
from scripts.common import banner


def print_summary(data: dict[str, Any]) -> None:
    run = data.get("run", {})
    totals = data.get("totals", {})
    print(f"\n  실행: {run.get('run_id')} ({run.get('status')})")
    print(
        f"  전체: {totals.get('sessions', 0)}세션 / 전환 {totals.get('converted', 0)}건 "
        f"({totals.get('conversion_rate', 0) * 100:.1f}%) / 폴백 {totals.get('degraded', 0)}건"
    )

    print("\n  전략별")
    cols = ("전략", "세션", "전환", "전환율", "평균턴", "신뢰", "인용률")
    header = (
        f"{cols[0]:<22} {cols[1]:>4} {cols[2]:>4} {cols[3]:>7} "
        f"{cols[4]:>6} {cols[5]:>5} {cols[6]:>7}"
    )
    print(f"    {header}")
    for row in data.get("by_strategy", []):
        print(
            f"    {row['strategy_id'] + ' ' + row['name']:<22} {row['sessions']:>4} "
            f"{row['converted']:>4} {row['conversion_rate'] * 100:>6.1f}% "
            f"{row['avg_turns_to_decision']:>6.2f} {row['avg_trust']:>5.2f} "
            f"{row['asset_citation_rate'] * 100:>6.1f}%"
        )

    strategies = [r["strategy_id"] for r in data.get("by_strategy", [])]
    if strategies:
        print("\n  페르소나 × 전략 (전환율)")
        print("    " + " " * 24 + "".join(f"{s:>8}" for s in strategies))
        for row in data.get("heatmap", []):
            label = f"{row['persona_id']} {row['persona_name']}"
            cells = "".join(
                f"{row['cells'].get(s, {}).get('conversion_rate', 0) * 100:>7.0f}%"
                for s in strategies
            )
            print(f"    {label:<24}{cells}")

    drops = data.get("drop_reasons", [])
    if drops:
        print("\n  이탈 사유")
        for row in drops:
            print(f"    {row['reason']:<14} {row['count']}건")

    mode = data.get("simulation_mode", {})
    print(f"\n  시뮬레이션 모드: {'LLM' if mode.get('llm_enabled') else '규칙 모델'}")
    print(f"  주의: {mode.get('caveat', '')}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Persona Bot Lab 시뮬레이션")
    ap.add_argument("--runs", type=int, default=None, help="페르소나×전략 당 반복 횟수")
    ap.add_argument("--concurrency", type=int, default=None, help="동시 실행 세션 수")
    ap.add_argument("--max-turns", type=int, default=None, help="세션당 최대 턴")
    ap.add_argument("--personas", default=None, help="쉼표 구분 페르소나 id (예: P2,P5)")
    ap.add_argument("--strategies", default=None, help="쉼표 구분 전략 id (예: S1,S2)")
    ap.add_argument("--summary-only", action="store_true", help="최근 실행 결과만 출력")
    args = ap.parse_args()

    banner("Persona Bot Lab")
    init_db()

    if args.summary_only:
        run_id = latest_run_id()
        if run_id is None:
            print("  실행 기록이 없다. 먼저 `python -m scripts.run_lab` 을 실행하라.")
            return 1
        print_summary(summarize(run_id))
        return 0

    problems = validate_bindings()
    if problems:
        print(f"  ! 페르소나 바인딩 문제: {problems}")

    config = LabConfig.from_settings(
        runs_per_pair=args.runs,
        concurrency=args.concurrency,
        max_turns=args.max_turns,
        persona_ids=args.personas.split(",") if args.personas else None,
        strategy_ids=args.strategies.split(",") if args.strategies else None,
    )
    settings = get_settings()
    print(
        f"  {len(config.persona_ids)} 페르소나 × {len(config.strategy_ids)} 전략 × "
        f"{config.runs_per_pair}회 = {config.total_sessions}세션 "
        f"(동시성 {config.concurrency}, 최대 {config.max_turns}턴)"
    )
    llm_note = f"연결됨 ({settings.llm_model})" if settings.llm_enabled else "미연결 → 규칙 모델"
    print(f"  LLM: {llm_note}")

    run_id = run_lab(config)
    print_summary(summarize(run_id))
    print("\n  대시보드: http://localhost:8000/lab")
    return 0


if __name__ == "__main__":
    sys.exit(main())
