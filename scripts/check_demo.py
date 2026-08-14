"""데모 시나리오 검증 — 발표 직전 리허설.

3종 시나리오를 실제 오케스트레이터로 돌리고 `expect` 블록을 검증한다.
하나라도 실패하면 exit 1 이다(발표 대본이 깨진 상태로 무대에 오르지 않게).

    python -m scripts.check_demo
    python -m scripts.check_demo --verbose   # 상담 문구 전문까지 출력
"""

from __future__ import annotations

import argparse
import sys

from app.demo import build_request, check_expectations, load_scenarios, pick_session
from app.services.orchestrator import Orchestrator
from scripts.common import banner


def main() -> int:
    ap = argparse.ArgumentParser(description="데모 시나리오 3종 검증")
    ap.add_argument("--verbose", action="store_true", help="상담 문구 전문 출력")
    args = ap.parse_args()

    banner("데모 시나리오 검증")
    scenarios = load_scenarios()
    if not scenarios:
        print("  ! data/demo_scenarios.yaml 이 없다")
        return 1

    orchestrator = Orchestrator()
    failures = 0
    for scenario in scenarios.values():
        session = pick_session(scenario)
        result = orchestrator.advise(build_request(scenario))
        problems = check_expectations(scenario, result)
        mark = "PASS" if not problems else "FAIL"
        print(f"\n  [{mark}] {scenario.id} {scenario.title}")
        print(
            f"        고객 {scenario.customer_id} / 상품 {scenario.target_product_id} / "
            f"세션 {session.session_id if session else '없음'} / 전략 {scenario.strategy_id}"
        )
        print(
            f"        결과: {result.hesitation_type.value} ({result.confidence:.2f}) / "
            f"CTA {result.cta.value} / 인용 {result.cited_asset_ids or '없음'} / "
            f"degraded={result.degraded}"
        )
        if result.citations:
            top = result.citations[0]
            print(
                f"        근거: {top.product_name} 컨디션 {top.condition_score}점 / "
                f"케어 {top.next_service_months}개월 / {top.headline_finding}"
            )
        if args.verbose:
            print(f"        문구: {result.message}")
        for problem in problems:
            print(f"        ! {problem}")
        failures += bool(problems)

    print(f"\n  {len(scenarios) - failures}/{len(scenarios)} 시나리오 통과")
    if failures:
        print("  → 발표 전에 반드시 고쳐야 한다. data/demo_scenarios.yaml 의 expect 블록 참고")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
