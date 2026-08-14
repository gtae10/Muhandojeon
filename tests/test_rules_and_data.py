"""규칙 엔진과 시드 픽스처 무결성 검증.

데모가 깨지는 조건(픽스처 규모, 71점 자산, 시나리오 라벨, provider 경계)을 테스트로 못박는다.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.config import REFERENCE_NOW
from app.data.provider import DatasetProvider, FixtureProvider, build_provider
from app.domain import CARE_THRESHOLD, condition_score, findings_for, next_service_months
from app.intent_rules import classify
from app.store import get_store
from contracts.common import EventType, HesitationType, ProductCategory, SessionEvent


def _event(kind: EventType, minute: int, **meta: object) -> SessionEvent:
    return SessionEvent(
        event_type=kind,
        product_id=meta.pop("product_id", "LX-0001"),
        timestamp=REFERENCE_NOW - timedelta(minutes=60 - minute),
        dwell_seconds=meta.pop("dwell", 60.0),
        meta=meta,
    )


# ── 인텐트 규칙 ────────────────────────────────────────────────
def test_size_guide_repeat_yields_size_uncertain():
    events = [
        _event(EventType.VIEW_PRODUCT, 1),
        _event(EventType.SIZE_GUIDE, 2, size="38"),
        _event(EventType.SIZE_GUIDE, 3, size="38.5"),
        _event(EventType.ADD_TO_CART, 4),
    ]
    result = classify(events)
    assert result.hesitation_type is HesitationType.SIZE_UNCERTAIN
    assert result.confidence > 0.7
    assert any(s.name == "size_guide_repeat" for s in result.signals)
    assert any(s.name == "cart_without_checkout" for s in result.signals)


def test_price_filter_yields_price_hesitant():
    events = [
        _event(EventType.VIEW_PRODUCT, 1),
        _event(EventType.PRICE_FILTER_CHANGE, 2, product_id=None, max_price_krw=3_000_000),
        _event(EventType.VIEW_PRODUCT, 3, product_id="LX-0002", cheaper_alternative=True),
    ]
    assert classify(events).hesitation_type is HesitationType.PRICE_HESITANT


def test_stock_check_yields_stock_concern():
    events = [_event(EventType.VIEW_PRODUCT, 1), _event(EventType.STOCK_CHECK, 2)]
    assert classify(events).hesitation_type is HesitationType.STOCK_CONCERN


def test_wide_browsing_yields_style_doubt():
    events = [
        _event(EventType.VIEW_PRODUCT, i, product_id=f"LX-{i:04d}", dwell=90.0) for i in range(1, 6)
    ] + [_event(EventType.BACK_TO_CATEGORY, 6, product_id=None) for _ in range(2)]
    assert classify(events).hesitation_type is HesitationType.STYLE_DOUBT


def test_empty_events_is_none_not_crash():
    result = classify([])
    assert result.hesitation_type is HesitationType.NONE
    assert result.signals


# ── 컨디션 규칙 (보류된 빌더·레거시 매퍼가 쓰는 계산) ─────────────
def test_condition_is_deterministic_and_category_sensitive():
    purchased = REFERENCE_NOW - timedelta(days=365 * 3)
    shoes = condition_score(purchased, REFERENCE_NOW, ProductCategory.SHOES, "AS-0001")
    bag = condition_score(purchased, REFERENCE_NOW, ProductCategory.BAG, "AS-0001")
    assert shoes < bag, "같은 연수라면 신발이 가방보다 낮아야 한다"
    assert shoes == condition_score(purchased, REFERENCE_NOW, ProductCategory.SHOES, "AS-0001")


def test_near_threshold_findings_flag_proximity():
    findings = findings_for(71, ProductCategory.BAG)
    assert findings
    assert "임계 근접" in findings[0].note
    assert next_service_months(71, ProductCategory.BAG, "AS-0001") >= 1
    assert next_service_months(CARE_THRESHOLD, ProductCategory.BAG, "AS-0001") == 0


# ── provider 경계 ─────────────────────────────────────────────
def test_fixture_provider_is_the_only_fixture_reader():
    provider = build_provider("fixture")
    assert isinstance(provider, FixtureProvider)
    assert provider.name == "fixture"
    assert len(provider.get_products()) == 12
    assert len(provider.get_customers()) == 6
    assert len(provider.get_assets()) == 18
    assert len(provider.get_scenarios()) == 3
    assert len(provider.get_assets("CU-0001")) == 5


def test_dataset_provider_is_an_explicit_stub():
    """데이터셋 미확정. 조용히 빈 결과를 주지 않고 명시적으로 실패해야 한다."""
    provider = build_provider("dataset")
    assert isinstance(provider, DatasetProvider)
    for call in (
        provider.get_products,
        provider.get_customers,
        provider.get_assets,
        provider.get_scenarios,
    ):
        with pytest.raises(NotImplementedError):
            call()


def test_seed_product_exposes_stock_and_last_code():
    provider = build_provider("fixture")
    by_id = {p.product_id: p for p in provider.get_products()}
    oxford = by_id["LX-0006"]
    assert oxford.last_code == "LAST-AURELIA"
    assert oxford.stock_by_size["38"] == 0
    assert "38" not in oxford.available_sizes, "재고 0 은 가용 사이즈에서 빠져야 한다"
    assert "Aurelia" in oxford.size_system
    shoulder = by_id["LX-0002"]
    assert shoulder.is_scarce, "재고 2점 이하면 희소로 판정해야 한다(S3 문구의 사실 근거)"


# ── 시드 무결성 (데모 전제) ────────────────────────────────────
def test_store_loads_fixtures_without_errors():
    store = get_store()
    stats = store.stats()
    assert stats["load_errors"] == []
    assert stats["seed_source"] == "fixture"
    assert (stats["products"], stats["customers"], stats["assets"], stats["sessions"]) == (
        12,
        6,
        18,
        3,
    )
    tiers = {c.tier.value for c in store.customers.values()}
    assert tiers == {"NEW", "ESTABLISHED", "VIP"}
    assert len({p.name for p in store.products.values()}) == 12
    assert all(1_500_000 <= p.price_krw <= 12_000_000 for p in store.products.values())


def test_demo_pinned_asset_exists():
    """발표 대본 핵심 대사: 컨디션 71점 + 핸들 마모 임계 근접."""
    store = get_store()
    matches = [
        a
        for a in store.assets.values()
        if a.condition_score == 71
        and a.category is ProductCategory.BAG
        and any("핸들" in f.note for f in a.findings)
    ]
    assert matches, "컨디션 71점 핸들 마모 자산이 없다 (fixtures/assets.json 확인)"
    assert matches[0].next_service_months <= 3


def test_contrast_assets_exist():
    """대비용 신품급(90+)과 리세일 시나리오용 저컨디션(<60)."""
    scores = [a.condition_score for a in get_store().assets.values()]
    assert max(scores) >= 90
    assert min(scores) < 60


def test_scenario_labels_are_derived_from_events():
    """라벨을 픽스처에 적어 두는 것이 아니라 이벤트에서 규칙으로 도출한다."""
    store = get_store()
    expected = {
        "SC-SIZE": "SIZE_UNCERTAIN",
        "SC-PRICE": "PRICE_HESITANT",
        "SC-STOCK": "STOCK_CONCERN",
    }
    for session_id, label in expected.items():
        record = store.sessions[session_id]
        assert record.hesitation_label == label
        assert record.label_matches_hint
        assert 8 <= len(record.events) <= 15
        assert record.signals


def test_same_last_asset_supports_size_consultation():
    """P3 시나리오의 근거: 대상과 같은 last_code 개체를 고객이 보유."""
    store = get_store()
    same_last = store.same_last_assets("CU-0003", "LX-0006")
    assert [a.asset_id for a in same_last] == ["AS-0010"]


def test_fixture_timestamps_are_fixed_not_now():
    """이벤트 시각이 고정값이어야 LLM 프롬프트 캐시가 유지된다."""
    store = get_store()
    for record in store.sessions.values():
        for event in record.events:
            assert event.timestamp <= REFERENCE_NOW


@pytest.mark.parametrize("strategy_id", ["S1", "S2", "S3"])
def test_strategies_load(strategy_id):
    from app.strategies import get_strategy

    strategy = get_strategy(strategy_id)
    assert strategy.id == strategy_id
    assert strategy.instructions
