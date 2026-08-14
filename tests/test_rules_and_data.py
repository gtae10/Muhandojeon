"""규칙 엔진·데이터 무결성·품질 게이트 검증.

데모가 깨지는 조건(고정 상품 40개, 컨디션 71점 자산, 라벨 5종)을 테스트로 못박는다.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pytest
from PIL import Image, ImageFilter

from app.config import REFERENCE_NOW
from app.domain import CARE_THRESHOLD, condition_score, findings_for, next_service_months
from app.intent_rules import classify
from app.store import get_store
from contracts.common import EventType, HesitationType, ProductCategory, SessionEvent
from scripts.register_fingerprint import measure


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
    result = classify(events)
    assert result.hesitation_type is HesitationType.PRICE_HESITANT


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


# ── 컨디션 규칙 ────────────────────────────────────────────────
def test_condition_is_deterministic_and_category_sensitive():
    purchased = REFERENCE_NOW - timedelta(days=365 * 3)
    shoes = condition_score(purchased, REFERENCE_NOW, ProductCategory.SHOES, "AS-000001")
    bag = condition_score(purchased, REFERENCE_NOW, ProductCategory.BAG, "AS-000001")
    assert shoes < bag, "같은 연수라면 신발이 가방보다 낮아야 한다"
    assert shoes == condition_score(purchased, REFERENCE_NOW, ProductCategory.SHOES, "AS-000001")


def test_near_threshold_findings_flag_proximity():
    findings = findings_for(71, ProductCategory.BAG)
    assert findings
    assert "임계 근접" in findings[0].note
    assert next_service_months(71, ProductCategory.BAG, "AS-000001") >= 1
    assert next_service_months(CARE_THRESHOLD, ProductCategory.BAG, "AS-000001") == 0


# ── 데이터 무결성 (데모 전제) ────────────────────────────────────
def test_catalog_and_customers_are_intact():
    store = get_store()
    assert len(store.products) == 40, "카탈로그 40개가 데모 화면 전제다"
    assert len({p.name for p in store.products.values()}) == 40, "상품명 중복 금지"
    assert len(store.customers) == 30
    tiers = {c.tier.value for c in store.customers.values()}
    assert tiers == {"NEW", "ESTABLISHED", "VIP"}, "페르소나 바인딩에 3개 티어가 모두 필요하다"
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
    assert matches, "컨디션 71점 핸들 마모 자산이 없다 (build_customers 보정 확인)"
    assert matches[0].next_service_months <= 3


def test_sessions_cover_all_labels():
    store = get_store()
    assert len(store.sessions) == 60
    labels = {s.hesitation_label for s in store.sessions.values()}
    assert labels == {h.value for h in HesitationType}, f"라벨 누락: {labels}"


# ── 지문 품질 게이트 ──────────────────────────────────────────
def test_quality_gate_rejects_blur_and_low_resolution(tmp_path):
    rng = np.random.default_rng(0)
    sharp_arr = rng.integers(70, 190, size=(1000, 1000), dtype=np.uint8)
    sharp = Image.fromarray(sharp_arr, "L").convert("RGB")

    ok_path = tmp_path / "handle_01.jpg"
    sharp.save(ok_path, quality=95)
    assert measure(ok_path, "handle", 1).passed

    blurred = tmp_path / "handle_02.jpg"
    sharp.filter(ImageFilter.GaussianBlur(5)).save(blurred, quality=95)
    result = measure(blurred, "handle", 2)
    assert not result.passed and "흐림" in result.reason

    small = tmp_path / "handle_03.jpg"
    sharp.resize((300, 300)).save(small, quality=95)
    assert "해상도 부족" in measure(small, "handle", 3).reason

    bright = tmp_path / "handle_04.jpg"
    Image.fromarray(np.full((1000, 1000), 254, dtype=np.uint8), "L").convert("RGB").save(bright)
    reason = measure(bright, "handle", 4).reason
    assert "과노출" in reason and "밝기 이탈" in reason


@pytest.mark.parametrize("strategy_id", ["S1", "S2", "S3"])
def test_strategies_load(strategy_id):
    from app.strategies import get_strategy

    strategy = get_strategy(strategy_id)
    assert strategy.id == strategy_id
    assert strategy.instructions
