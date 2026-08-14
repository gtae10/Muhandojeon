"""LLM 캐시 워밍업 — 네트워크가 끊겨도 데모가 돌아가게 한다.

`DEMO_MODE=true` 면 모든 LLM 호출 결과가 `.cache/llm/` 에 저장되고 동일 입력은 캐시에서
반환된다. 이 스크립트로 **3종 시나리오와 Persona Bot Lab 45세션을 미리 실행**해 캐시를 채운다.

    DEMO_MODE=true python -m scripts.warm_cache
    DEMO_MODE=true python -m scripts.warm_cache --skip-lab   # 시나리오만
    make demo                                                # 워밍업 + 서버 기동

LLM 키가 없으면 호출 자체가 없으므로 캐시는 비어 있고, 그래도 데모는 결정적 템플릿으로
완주한다(캐시가 없어도 화면이 깨지지 않는다는 뜻).
"""

from __future__ import annotations

import argparse
import sys
import time

from app.config import get_settings
from app.db import init_db
from app.demo import build_request, check_expectations, load_scenarios
from app.lab.cost import estimate_lab_cost
from app.lab.runner import LabConfig, run_lab
from app.lab.summary import summarize
from app.llm import get_budget, get_llm
from app.services.orchestrator import Orchestrator
from scripts.common import banner


def main() -> int:
    ap = argparse.ArgumentParser(description="데모 캐시 워밍업")
    ap.add_argument("--skip-lab", action="store_true", help="Lab 45세션을 건너뛴다")
    ap.add_argument("--runs", type=int, default=None, help="Lab 반복 횟수")
    ap.add_argument("--yes", action="store_true", help="예상 비용 확인 없이 진행")
    args = ap.parse_args()

    banner("데모 캐시 워밍업")
    settings = get_settings()
    llm = get_llm()
    init_db()

    print(f"  DEMO_MODE={settings.demo_mode} / LLM={'연결' if settings.llm_enabled else '미연결'}")
    if not settings.demo_mode:
        print("  ! DEMO_MODE 가 false 다. 캐시에 쓰이지 않는다 → `DEMO_MODE=true` 로 실행하라")
    before = llm.cache_count()
    print(f"  캐시 시작 건수: {before}")

    started = time.perf_counter()
    orchestrator = Orchestrator()
    scenarios = load_scenarios()
    print(f"\n  시나리오 {len(scenarios)}종 예비 실행")
    failures = 0
    for scenario in scenarios.values():
        result = orchestrator.advise(build_request(scenario))
        problems = check_expectations(scenario, result)
        failures += bool(problems)
        print(
            f"    {'ok  ' if not problems else 'FAIL'} {scenario.id} "
            f"{scenario.title[:28]:<30} 인용 {len(result.cited_asset_ids)}건 / "
            f"CTA {result.cta.value}"
        )
        for problem in problems:
            print(f"         ! {problem}")

    if not args.skip_lab:
        config = LabConfig.from_settings(runs_per_pair=args.runs)
        # 실제 과금이 발생하는 상태(키 연결 + 드라이런 아님)에서만 확인을 요구한다.
        if settings.llm_enabled and not settings.llm_dry_run:
            estimate = estimate_lab_cost(config.total_sessions, config.max_turns)
            budget = get_budget().state(refresh=True)
            print(
                f"\n  Lab 예비 실행 예상 비용: ${estimate['total_usd']:.4f} "
                f"(≈{estimate['total_krw']:,.0f}원) / 하드 잔액 ${budget.remaining_to_hard:.4f}"
            )
            if estimate["total_usd"] > budget.remaining_to_hard:
                print("  ! 하드 리밋 잔액 초과 → Lab 워밍업을 건너뛴다(시나리오 캐시는 채웠다)")
                args.skip_lab = True
            elif not args.yes:
                if not sys.stdin.isatty():
                    print("  ! 확인이 필요하다. --yes 를 붙이거나 --skip-lab 으로 실행하라")
                    return 1
                if input("  이 비용으로 워밍업할까? [y/N] ").strip().lower() not in {"y", "yes"}:
                    print("  Lab 워밍업을 건너뛴다")
                    args.skip_lab = True
    if not args.skip_lab:
        config = LabConfig.from_settings(runs_per_pair=args.runs)
        print(f"\n  Persona Bot Lab {config.total_sessions}세션 예비 실행")
        run_id = run_lab(config)
        summary = summarize(run_id)
        totals = summary["totals"]
        print(
            f"    완료: {totals['sessions']}세션 / 전환 {totals['converted']}건 "
            f"({totals['conversion_rate'] * 100:.1f}%)"
        )

    elapsed = time.perf_counter() - started
    after = llm.cache_count()
    print(f"\n  캐시 {before} → {after} 건 (+{after - before}), 소요 {elapsed:.1f}초")
    print(f"  캐시 위치: {settings.llm_cache_dir}")
    print(f"  LLM 통계: {llm.stats.as_dict()}")
    if failures:
        print("  ! 시나리오 검증 실패가 있다 — `python -m scripts.check_demo` 로 확인하라")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
