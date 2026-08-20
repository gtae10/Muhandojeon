"""선제 오프닝(outreach) 계약 고정.

원칙: **계기(케어 임박 자산)가 있을 때만 먼저 말을 건다.** 계기가 없으면
`message: null` 이고 화면은 아무것도 띄우지 않는다 — 이 규약이 무너지면
클라이언텔링이 세일즈 봇이 된다. AI2 실서버의 400(계기 없음)도 같은 규약으로
흡수된다(어댑터 docstring 참조).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.clienteling_rules import OPENING_MONTHS, build_opening
from app.main import app
from contracts.clienteling import ClientelingOutreachRequest
from contracts.common import CTA, OwnedAsset


def _asset(asset_id: str, months: int, score: int = 80) -> OwnedAsset:
    return OwnedAsset(
        asset_id=asset_id,
        customer_id="CU-0001",
        product_id="LX-0001",
        product_name="Aurelia Top Handle",
        category="BAG",
        purchased_at="2022-04-16T00:00:00+09:00",
        condition_score=score,
        findings=[],
        next_service_months=months,
    )


def test_opening_requires_care_trigger() -> None:
    """케어 임박 자산이 없으면 message=None — 오프닝을 만들지 않는다."""
    request = ClientelingOutreachRequest(
        customer_id="CU-0001", owned_assets=[_asset("AS-0001", OPENING_MONTHS + 1)]
    )
    result = build_opening(request)
    assert result.message is None
    assert result.cited_asset_ids == []
    assert result.cta is CTA.NONE


def test_opening_cites_most_urgent_asset() -> None:
    """계기가 있으면 가장 임박한 자산을 인용하고 케어 CTA 를 단다."""
    request = ClientelingOutreachRequest(
        customer_id="CU-0001",
        owned_assets=[_asset("AS-0002", 2, score=85), _asset("AS-0001", 1, score=71)],
    )
    result = build_opening(request)
    assert result.message and "Aurelia Top Handle" in result.message
    assert "71점" in result.message
    assert result.cited_asset_ids == ["AS-0001"]
    assert result.cta is CTA.CARE_BOOKING


def test_opening_is_deterministic() -> None:
    """같은 자산 상태 → 항상 같은 문장 (데모 재현성)."""
    request = ClientelingOutreachRequest(
        customer_id="CU-0001", owned_assets=[_asset("AS-0001", 0, score=63)]
    )
    assert build_opening(request).message == build_opening(request).message


def test_endpoint_roundtrip_with_seed_assets() -> None:
    """시드 고객으로 실왕복 — 케어 임박 VIP 는 오프닝, 새 고객은 null."""
    with TestClient(app) as client:
        due = client.get("/assets/CU-0001").json()["assets"]  # 케어 임박 자산 보유(VIP)
        opened = client.post(
            "/clienteling/outreach", json={"customer_id": "CU-0001", "owned_assets": due}
        )
        assert opened.status_code == 200
        assert opened.headers["x-degraded"] == "false"
        body = opened.json()
        assert body["message"]
        assert body["cited_asset_ids"], "오프닝이 자산 근거 없이 나갔다"
        assert body["cta"] == "CARE_BOOKING"

        fresh = client.get("/assets/CU-0005").json()["assets"]  # NEW, 컨디션 97점
        silent = client.post(
            "/clienteling/outreach", json={"customer_id": "CU-0005", "owned_assets": fresh}
        )
        assert silent.status_code == 200
        assert silent.json()["message"] is None
