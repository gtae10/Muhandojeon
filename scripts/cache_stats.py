"""LLM 캐시 히트율과 절감액.

**Persona Bot Lab 을 두 번 돌렸을 때 히트율이 90% 미만이면 프롬프트에 비결정적 값이 섞인
것이다**(현재 시각·UUID·랜덤 id). 그러면 캐시가 사실상 동작하지 않고, 모르고 몇 번 돌리면
예산이 사라진다. 이 스크립트가 그 신호를 준다.

    python -m scripts.cache_stats
    python -m scripts.cache_stats --by-run     # 실행별 히트율
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db import init_db, session_scope
from app.llm import get_llm
from app.models import LlmUsageRow
from scripts.common import banner

MIN_HEALTHY_HIT_RATE = 0.9


def load_rows() -> list[dict[str, Any]]:
    with session_scope() as db:
        rows = db.execute(select(LlmUsageRow)).scalars().all()
        return [
            {
                "purpose": str(r.purpose),
                "model": str(r.model),
                "cached": bool(r.cached),
                "dry_run": bool(r.dry_run),
                "cost_usd": float(r.cost_usd),
                "run_id": r.run_id,
                "cache_key": str(r.cache_key),
                "note": str(r.note),
            }
            for r in rows
        ]


def rate(hits: int, lookups: int) -> float:
    return hits / lookups if lookups else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="LLM 캐시 통계")
    ap.add_argument("--by-run", action="store_true", help="Lab 실행별 히트율")
    args = ap.parse_args()

    banner("LLM 캐시 통계")
    init_db()
    settings = get_settings()
    rows = load_rows()
    llm = get_llm()

    print(f"  캐시 활성화: {settings.llm_cache_enabled} / 디스크 항목 {llm.cache_count()}건")
    print(f"  캐시 위치: {settings.llm_cache_dir}")
    if not rows:
        if not settings.llm_active:
            print(
                "\n  호출 기록이 없다 — LLM 미연결(LLM_API_KEY 없음)이라 모든 응답이 결정적 "
                "템플릿·규칙으로 처리됐다. 비용도 0 이다."
            )
            print(
                "  호출 패턴을 보려면: make estimate (드라이런) 또는 LLM_API_KEY 설정 후 make lab"
            )
        else:
            print("\n  기록이 없다. `make estimate` 또는 `make lab` 을 먼저 실행하라.")
        return 0

    lookups = [r for r in rows if not r["dry_run"] or r["cached"]]
    hits = [r for r in rows if r["cached"]]
    billed = [r for r in rows if not r["cached"] and not r["dry_run"]]
    saved = sum(r["cost_usd"] for r in hits)
    spent = sum(r["cost_usd"] for r in billed)

    print(
        f"\n  전체: 조회 {len(lookups)}건 / 히트 {len(hits)}건 "
        f"({rate(len(hits), len(lookups)) * 100:.1f}%) / 실제 청구 {len(billed)}건"
    )
    print(f"  지출 ${spent:.4f} / 캐시로 아낀 금액 ${saved:.4f}")

    print("\n  용도별")
    print(f"    {'용도':<15} {'조회':>5} {'히트':>5} {'히트율':>7} {'지출':>10} {'절감':>10}")
    problems: list[str] = []
    for purpose in sorted({r["purpose"] for r in rows}):
        subset = [r for r in rows if r["purpose"] == purpose]
        p_lookups = [r for r in subset if not r["dry_run"] or r["cached"]]
        p_hits = [r for r in subset if r["cached"]]
        p_spent = sum(r["cost_usd"] for r in subset if not r["cached"] and not r["dry_run"])
        p_saved = sum(r["cost_usd"] for r in p_hits)
        hit_rate = rate(len(p_hits), len(p_lookups))
        print(
            f"    {purpose:<15} {len(p_lookups):>5} {len(p_hits):>5} {hit_rate * 100:>6.1f}% "
            f"${p_spent:>9.4f} ${p_saved:>9.4f}"
        )
        # 같은 프롬프트가 두 번 이상 조회됐는데 히트율이 낮으면 키가 흔들린 것이다.
        keys = [r["cache_key"] for r in subset if r["cache_key"]]
        if len(keys) >= 2 and len(set(keys)) == len(keys) and len(p_lookups) >= 4:
            problems.append(
                f"{purpose}: 캐시 키가 전부 달라 히트가 없다 → 프롬프트에 비결정적 값 의심"
            )
        elif len(p_lookups) >= 4 and hit_rate < MIN_HEALTHY_HIT_RATE and len(p_hits) == 0:
            problems.append(f"{purpose}: 히트율 {hit_rate * 100:.0f}% (첫 실행이면 정상)")

    if args.by_run:
        by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row["run_id"]:
                by_run[str(row["run_id"])].append(row)
        print("\n  Lab 실행별")
        for run_id in sorted(by_run):
            subset = by_run[run_id]
            r_hits = [r for r in subset if r["cached"]]
            print(
                f"    {run_id:<24} 조회 {len(subset):>4} / 히트 {len(r_hits):>4} "
                f"({rate(len(r_hits), len(subset)) * 100:>5.1f}%) "
                f"지출 ${sum(r['cost_usd'] for r in subset if not r['cached']):.4f}"
            )
        if len(by_run) >= 2:
            latest = sorted(by_run)[-1]
            subset = by_run[latest]
            hit_rate = rate(len([r for r in subset if r["cached"]]), len(subset))
            verdict = "정상" if hit_rate >= MIN_HEALTHY_HIT_RATE else "점검 필요"
            print(
                f"\n  재실행 히트율({latest}): {hit_rate * 100:.1f}% → {verdict} "
                f"(기준 {MIN_HEALTHY_HIT_RATE * 100:.0f}%)"
            )
            if hit_rate < MIN_HEALTHY_HIT_RATE:
                problems.append(
                    f"재실행 히트율 {hit_rate * 100:.0f}% < 90% — "
                    "프롬프트의 비결정적 값을 찾아 제거하라"
                )

    if problems:
        print("\n  점검 항목")
        for problem in problems:
            print(f"    ! {problem}")
    else:
        print("\n  이상 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main())
