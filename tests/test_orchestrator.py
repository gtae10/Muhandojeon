"""오케스트레이터 검증 — 인용 검증(5단계)이 이 서비스의 존재 이유를 지키는지."""

from __future__ import annotations

import pytest

from app.adapters.base import UpstreamError
from app.services.orchestrator import Orchestrator, ProductNotFound, rank_assets
from app.store import get_store
from contracts.assets import CustomerAssetsResponse
from contracts.clienteling import ClientelingReplyRequest, ClientelingReplyResponse
from contracts.common import CTA, CustomerTier
from contracts.orchestrator import AdviseRequest


@pytest.fixture
def store():
    return get_store()


@pytest.fixture
def pinned(store):
    """데모 대본용 자산(컨디션 71점, 핸들 마모 임계 근접)을 가진 고객."""
    for customer in store.customers.values():
        for asset in customer.assets:
            if asset.condition_score == 71 and asset.category.value == "BAG":
                return customer, asset
    pytest.fail("컨디션 71점 가방 자산이 없다 — build_customers 의 데모 보정이 깨졌다")


def _request(
    customer_id: str, product_id: str, strategy: str, *, events: bool = True
) -> AdviseRequest:
    """세션 이벤트는 계약상 비울 수 있다(일반 제안 모드). 기본은 1건을 넣어 AI1 을 실제로 태운다."""
    from datetime import timedelta

    from app.config import REFERENCE_NOW
    from contracts.common import EventType, SessionEvent

    session_events = (
        [
            SessionEvent(
                event_type=EventType.SIZE_GUIDE,
                product_id=product_id,
                timestamp=REFERENCE_NOW - timedelta(minutes=5),
                dwell_seconds=80.0,
                meta={"size": "38"},
            ),
            SessionEvent(
                event_type=EventType.SIZE_GUIDE,
                product_id=product_id,
                timestamp=REFERENCE_NOW - timedelta(minutes=3),
                dwell_seconds=60.0,
                meta={"size": "38.5"},
            ),
        ]
        if events
        else []
    )
    return AdviseRequest(
        customer_id=customer_id,
        target_product_id=product_id,
        session_events=session_events,
        strategy_id=strategy,
    )


def test_empty_session_events_uses_general_mode(store):
    """이벤트 없이 호출해도 크래시하지 않고 NONE 으로 처리한다(계약이 허용하는 입력)."""
    product_id = next(iter(store.products))
    result = Orchestrator().advise(_request("CU-0001", product_id, "S2", events=False))
    assert result.hesitation_type.value == "NONE"
    steps = {s.step: s for s in result.trace}
    assert steps["intent"].adapter == "skipped"


def test_s2_cites_owned_assets(store, pinned):
    customer, asset = pinned
    product_id = next(iter(store.products))
    result = Orchestrator().advise(_request(customer.customer_id, product_id, "S2"))
    assert result.owned_assets_used is True
    assert result.cited_asset_ids
    assert result.citations[0].condition_score <= 100
    assert result.no_assets is False


def test_s1_does_not_cite_and_flag_is_false(store, pinned):
    customer, _ = pinned
    product_id = next(iter(store.products))
    result = Orchestrator().advise(_request(customer.customer_id, product_id, "S1"))
    # S1 은 전략상 자산을 인용하지 않는다. 플래그가 false 로 관측되는 것이 정상이다.
    assert result.cited_asset_ids == []
    assert result.owned_assets_used is False
    assert result.no_assets is False


def test_hallucinated_citation_is_dropped(store, pinned):
    """소유하지 않은 개체 id 를 인용하면 제거된다."""
    customer, _ = pinned
    product_id = next(iter(store.products))

    class Liar:
        def __init__(self) -> None:
            from app.adapters.base import AdapterStatus

            self.status = AdapterStatus(name="Liar", module="clienteling", mode="mock")

        def reply(self, request: ClientelingReplyRequest) -> ClientelingReplyResponse:
            return ClientelingReplyResponse(
                message="존재하지 않는 개체를 근거로 든 응답",
                cited_asset_ids=["AS-9999"],
                cta=CTA.CARE_BOOKING,
                reasoning="test",
            )

        def outreach(self, request):  # noqa: ANN001, ANN201 — 포트 충족용, 이 테스트에선 미사용
            raise NotImplementedError

    orch = Orchestrator(clienteling=Liar())
    result = orch.advise(_request(customer.customer_id, product_id, "S2"))
    assert result.cited_asset_ids == []
    assert result.owned_assets_used is False
    # 근거가 사라졌으면 케어 예약 CTA 도 유지하지 않는다.
    assert result.cta is not CTA.CARE_BOOKING


def test_upstream_failure_degrades_without_error(store, pinned):
    """업스트림이 죽어도 응답은 나오고 degraded 로 표시된다(발표 중 에러 화면 금지)."""
    customer, _ = pinned
    product_id = next(iter(store.products))

    class Broken:
        def __init__(self, module: str) -> None:
            from app.adapters.base import AdapterStatus

            self.status = AdapterStatus(name="Broken", module=module, mode="http")

        def classify(self, request):  # noqa: ANN001, ANN201
            raise UpstreamError("연결 실패")

        def reply(self, request):  # noqa: ANN001, ANN201
            raise UpstreamError("연결 실패")

        def outreach(self, request):  # noqa: ANN001, ANN201
            raise UpstreamError("연결 실패")

    orch = Orchestrator(intent=Broken("intent"), clienteling=Broken("clienteling"))
    result = orch.advise(_request(customer.customer_id, product_id, "S2"))
    assert result.degraded is True
    assert result.message  # 폴백 문구가 채워져 있다
    steps = {s.step: s for s in result.trace}
    assert steps["intent"].degraded is True
    assert steps["clienteling"].degraded is True


def test_new_tier_customer_sets_no_assets_when_empty(store):
    class Empty:
        def __init__(self) -> None:
            from app.adapters.base import AdapterStatus

            self.status = AdapterStatus(name="Empty", module="asset", mode="mock")

        def assets(self, customer_id: str) -> CustomerAssetsResponse:
            return CustomerAssetsResponse(customer_id=customer_id, tier=CustomerTier.NEW, assets=[])

    product_id = next(iter(store.products))
    result = Orchestrator(assets=Empty()).advise(_request("CU-0001", product_id, "S2"))
    assert result.no_assets is True
    assert result.owned_assets_used is False


def test_unknown_product_raises(store):
    with pytest.raises(ProductNotFound):
        Orchestrator().advise(_request("CU-0001", "LX-9999", "S2"))


def test_ranking_prefers_care_due_and_same_category(store):
    customer = store.customers["CU-0001"]
    target = next(p for p in store.products.values() if p.category.value == "BAG")
    ranked = rank_assets(customer.assets, target)
    assert ranked[0].priority >= ranked[-1].priority
    # 1순위는 케어가 임박하거나 같은 카테고리여야 한다.
    top = ranked[0]
    assert top.next_service_months <= 6 or top.category is target.category
