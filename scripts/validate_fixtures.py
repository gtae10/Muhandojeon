"""픽스처 검증 — 손으로 쓴 시드 데이터의 오타·정합성 오류를 발표 전날이 아니라 지금 잡는다.

검사 항목
    1. 계약 스키마 (provider 로딩 시 Pydantic 검증)
    2. 참조 정합성 (assets.product_id / customer_id, 시나리오의 고객·상품, 이벤트의 상품)
    3. id 유일성, 값 범위(가격 대역·컨디션 0~100·재고 음수 금지)
    4. **데모 전제**: 컨디션 71점 핸들 마모 / 90점 이상 / 60점 미만 자산이 각각 존재
    5. **라벨 도출**: 시나리오 이벤트에 규칙을 적용한 라벨이 `label_hint` 와 일치
    6. 페르소나 바인딩: 5종이 실제 고객에 붙어 있고 소유 자산이 있는지, P3 는 동일 last_code 보유
    7. 캐시 안전성: 이벤트 타임스탬프가 고정값인지(현재 시각이 섞이면 LLM 캐시가 무효화된다)

    python -m scripts.validate_fixtures
    python -m scripts.validate_fixtures --provider dataset   # 데이터셋 provider 로 같은 검사
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from app.config import REFERENCE_NOW
from app.data.provider import build_provider
from app.intent_rules import classify
from app.personas import load_personas
from app.strategies import load_strategies
from contracts.assets import CustomerAssetsResponse
from scripts.common import banner

PRICE_MIN, PRICE_MAX = 1_500_000, 12_000_000


def check(problems: list[str], condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


def main() -> int:  # noqa: PLR0912, PLR0915 - 검증 스크립트는 평탄한 편이 읽기 쉽다
    ap = argparse.ArgumentParser(description="시드 픽스처 검증")
    ap.add_argument("--provider", default=None, help="fixture | dataset (기본: SEED_SOURCE)")
    args = ap.parse_args()

    banner("픽스처 검증")
    problems: list[str] = []
    try:
        provider = build_provider(args.provider)
        products = provider.get_products()
        customers = provider.get_customers()
        assets = provider.get_assets()
        scenarios = provider.get_scenarios()
    except NotImplementedError as exc:
        print(f"  provider 미구현: {exc}")
        return 1
    except (OSError, ValueError) as exc:
        print(f"  ! 로딩 실패: {exc}")
        return 1

    print(
        f"  소스: {provider.name} — 상품 {len(products)} / 고객 {len(customers)} / "
        f"개체 {len(assets)} / 시나리오 {len(scenarios)}"
    )

    # ── 유일성·값 범위 ────────────────────────────────────────
    product_ids = [p.product_id for p in products]
    customer_ids = [c.customer_id for c in customers]
    asset_ids = [a.asset_id for a in assets]
    check(problems, len(set(product_ids)) == len(product_ids), "product_id 중복")
    check(problems, len(set(customer_ids)) == len(customer_ids), "customer_id 중복")
    check(problems, len(set(asset_ids)) == len(asset_ids), "asset_id 중복")
    check(
        problems,
        len({p.name for p in products}) == len(products),
        "상품명 중복 (발표 화면에서 구분이 안 된다)",
    )

    for product in products:
        check(
            problems,
            PRICE_MIN <= product.price_krw <= PRICE_MAX,
            f"{product.product_id}: 가격 {product.price_krw:,}원이 "
            f"대역({PRICE_MIN:,}~{PRICE_MAX:,}) 밖",
        )
        check(
            problems, bool(product.stock_by_size), f"{product.product_id}: stock_by_size 비어 있음"
        )
        check(
            problems,
            all(qty >= 0 for qty in product.stock_by_size.values()),
            f"{product.product_id}: 재고 음수",
        )
        check(problems, bool(product.last_code), f"{product.product_id}: last_code 없음")
        check(problems, bool(product.image_path), f"{product.product_id}: image_path 없음")

    # ── 참조 정합성 ───────────────────────────────────────────
    known_products = set(product_ids)
    known_customers = set(customer_ids)
    for asset in assets:
        check(
            problems,
            asset.product_id in known_products,
            f"{asset.asset_id}: 없는 product_id {asset.product_id}",
        )
        check(
            problems,
            asset.customer_id in known_customers,
            f"{asset.asset_id}: 없는 customer_id {asset.customer_id}",
        )
        check(
            problems,
            0 <= asset.condition_score <= 100,
            f"{asset.asset_id}: 컨디션 {asset.condition_score} 범위 밖",
        )
        check(
            problems,
            asset.next_service_months >= 0,
            f"{asset.asset_id}: next_service_months 음수",
        )
        check(
            problems,
            asset.purchased_at <= REFERENCE_NOW,
            f"{asset.asset_id}: 구매 시각이 기준시각({REFERENCE_NOW.date()}) 이후",
        )
        if asset.last_scanned_at is not None:
            check(
                problems,
                asset.purchased_at <= asset.last_scanned_at <= REFERENCE_NOW,
                f"{asset.asset_id}: last_scanned_at 이 구매~기준시각 범위 밖",
            )

    # 계약 응답이 실제로 만들어지는지 (GET /assets/{id} 모양)
    for customer in customers:
        owned = provider.get_assets(customer.customer_id)
        try:
            CustomerAssetsResponse(
                customer_id=customer.customer_id, tier=customer.tier, assets=owned
            )
        except Exception as exc:  # noqa: BLE001 - 검증 스크립트에서는 원인을 그대로 보고한다
            problems.append(f"{customer.customer_id}: CustomerAssetsResponse 생성 실패 — {exc}")

    # ── 데모 전제 ─────────────────────────────────────────────
    pinned = [
        a for a in assets if a.condition_score == 71 and any("핸들" in f.note for f in a.findings)
    ]
    check(problems, bool(pinned), "컨디션 71점 + 핸들 마모 자산이 없다 (데모 대본 핵심 대사)")
    if pinned:
        check(
            problems,
            pinned[0].next_service_months <= 3,
            f"{pinned[0].asset_id}: 71점인데 케어 시점이 "
            f"{pinned[0].next_service_months}개월 (임계 근접이 아니다)",
        )
    check(
        problems,
        any(a.condition_score >= 90 for a in assets),
        "컨디션 90점 이상 신품급 자산이 없다",
    )
    check(problems, any(a.condition_score < 60 for a in assets), "컨디션 60점 미만 자산이 없다")

    # ── 시나리오 라벨 도출 ─────────────────────────────────────
    for scenario in scenarios:
        check(
            problems,
            scenario.customer_id in known_customers,
            f"{scenario.scenario_id}: 없는 customer_id {scenario.customer_id}",
        )
        check(
            problems,
            scenario.target_product_id in known_products,
            f"{scenario.scenario_id}: 없는 target_product_id {scenario.target_product_id}",
        )
        check(
            problems,
            8 <= len(scenario.events) <= 15,
            f"{scenario.scenario_id}: 이벤트 {len(scenario.events)}개 (8~15개 권장)",
        )
        for event in scenario.events:
            if event.product_id is not None:
                check(
                    problems,
                    event.product_id in known_products,
                    f"{scenario.scenario_id}: 이벤트의 없는 product_id {event.product_id}",
                )
            check(
                problems,
                event.timestamp <= REFERENCE_NOW,
                f"{scenario.scenario_id}: 이벤트 시각이 기준시각 이후 ({event.timestamp})",
            )
        result = classify(scenario.events)
        check(
            problems,
            result.hesitation_type == scenario.label_hint,
            f"{scenario.scenario_id}: 규칙 라벨 {result.hesitation_type.value} ≠ 힌트 "
            f"{scenario.label_hint.value} — 이벤트 시퀀스가 의도한 유형을 드러내지 못한다",
        )
        print(
            f"    {scenario.scenario_id:<9} {scenario.title:<10} → "
            f"{result.hesitation_type.value:<15} "
            f"({result.confidence:.2f}) 이벤트 {len(scenario.events)}개 / "
            f"고객 {scenario.customer_id} / 대상 {scenario.target_product_id}"
        )

    # ── 페르소나·전략 바인딩 ───────────────────────────────────
    personas = load_personas()
    strategies = load_strategies()
    check(problems, len(personas) == 5, f"페르소나 {len(personas)}종 (5종이어야 한다)")
    check(problems, len(strategies) == 3, f"전략 {len(strategies)}종 (3종이어야 한다)")
    by_customer = {c.customer_id: c for c in customers}
    for persona in personas.values():
        bound = by_customer.get(persona.customer_id)
        if bound is None:
            problems.append(f"{persona.id}: 없는 고객 {persona.customer_id}")
            continue
        owned = provider.get_assets(persona.customer_id)
        check(
            problems,
            bool(owned),
            f"{persona.id}: 고객 {persona.customer_id} 에 소유 개체가 없다 (S2 검증 불가)",
        )
        check(
            problems,
            persona.target_product_id in known_products,
            f"{persona.id}: 없는 대상 상품 {persona.target_product_id}",
        )
        print(
            f"    {persona.id} {persona.name:<14} {bound.customer_id} "
            f"{bound.tier.value:<12} "
            f"개체 {len(owned)}개 / 대상 {persona.target_product_id}"
        )

    # P3(사이즈 불안형)은 동일 last_code 자산이 있어야 사이즈 근거가 성립한다.
    p3 = personas.get("P3")
    if p3:
        target = next((p for p in products if p.product_id == p3.target_product_id), None)
        owned_products = {
            a.product_id: next((p for p in products if p.product_id == a.product_id), None)
            for a in provider.get_assets(p3.customer_id)
        }
        same_last = [
            pid
            for pid, prod in owned_products.items()
            if prod is not None and target is not None and prod.last_code == target.last_code
        ]
        check(
            problems,
            bool(same_last),
            f"P3: 고객 {p3.customer_id} 에 대상({p3.target_product_id})과 "
            f"같은 last_code 자산이 없다",
        )

    # 페르소나 티어 요구 (P1 NEW·자산 1개 / P4 60점 미만 보유 / P5 자산 4개 이상)
    def owned_of(pid: str) -> list[Any]:
        persona = personas.get(pid)
        return provider.get_assets(persona.customer_id) if persona else []

    check(problems, len(owned_of("P1")) == 1, "P1: NEW 고객의 소유 개체가 1개여야 한다")
    check(
        problems,
        any(a.condition_score < 60 for a in owned_of("P4")),
        "P4: 컨디션 60점 미만 자산을 보유해야 한다(리세일 시나리오)",
    )
    check(problems, len(owned_of("P5")) >= 4, "P5: 소유 개체가 4개 이상이어야 한다")

    print()
    if problems:
        print(f"  문제 {len(problems)}건")
        for problem in problems:
            print(f"    ! {problem}")
        return 1
    print("  모든 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
