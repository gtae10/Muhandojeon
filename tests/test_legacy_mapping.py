"""팀 백엔드(이미 구현된 다른 스키마) 응답을 계약으로 매핑하는지 검증.

실제 레포(gtae10/Muhandojeon)의 `backend/` 응답 모양을 그대로 넣어 본다.
필드 차이 목록은 `docs/BACKEND_INTEGRATION.md` 참고.
"""

from __future__ import annotations

from app.adapters.assets import legacy_assets_mapper
from app.adapters.clienteling import legacy_clienteling_mapper
from app.adapters.condition import legacy_condition_mapper
from app.adapters.fingerprint import legacy_fingerprint_mapper
from app.adapters.intent import legacy_intent_mapper
from contracts.assets import CustomerAssetsResponse
from contracts.clienteling import ClientelingReplyResponse
from contracts.condition import ConditionScoreResponse
from contracts.fingerprint import FingerprintMatchResponse
from contracts.intent import IntentClassifyResponse


def test_assets_legacy_shape():
    raw = {
        "user_id": "CU-0007",
        "total": 1,
        "assets": [
            {
                "asset_id": "AS-000031",
                "product_id": "LX-0004",
                "product_name": "Aurelia Oxford",
                "brand": "Maison",
                "category": "bag",
                "purchase_date": "2023-04-18T00:00:00+09:00",
                "purchase_price": 2380.0,
                "condition_score": 71,
                "condition_grade": "Good",
                "wear_details": {"scratches": 4, "hardware_tarnish": True, "color_fade": False},
                "last_assessed": "2026-07-02T14:20:00+09:00",
                "notes": "",
            }
        ],
    }
    mapped = CustomerAssetsResponse.model_validate(legacy_assets_mapper(raw))
    assert mapped.customer_id == "CU-0007"
    assert mapped.tier.value == "NEW"  # 개체 1개 → NEW 로 추정
    asset = mapped.assets[0]
    assert asset.condition_score == 71
    assert asset.next_service_months >= 0
    parts = {f.part.value for f in asset.findings}
    assert "exterior" in parts and "hardware" in parts
    assert any("4건" in f.note for f in asset.findings)


def test_condition_legacy_grade_only():
    raw = {"asset_id": "AS-000031", "condition_grade": "Fair", "wear_detail": {"cracks": 1}}
    mapped = ConditionScoreResponse.model_validate(legacy_condition_mapper(raw))
    assert mapped.score == 62
    assert mapped.next_service_months == 0  # 70 이하 → 즉시 케어
    assert mapped.findings[0].severity.value == "HIGH"


def test_clienteling_legacy_reply_recovers_asset_ids():
    raw = {
        "session_id": "s1",
        "reply": "2023년 AS-000031 개체의 컨디션이 71점입니다. 케어를 권합니다.",
        "model_used": "gpt-4o",
    }
    mapped = ClientelingReplyResponse.model_validate(legacy_clienteling_mapper(raw))
    assert mapped.message.startswith("2023년")
    # cited_asset_ids 가 없는 응답에서 본문의 개체 id 를 회수한다.
    assert mapped.cited_asset_ids == ["AS-000031"]
    assert mapped.cta.value == "NONE"


def test_fingerprint_legacy_new_registration_is_not_match():
    raw = {"asset_id": "AS-000031", "condition_score": 88, "is_new_registration": True}
    mapped = FingerprintMatchResponse.model_validate(legacy_fingerprint_mapper(raw))
    assert mapped.is_match is False
    assert mapped.matched_asset_id is None

    raw2 = {"asset_id": "AS-000031", "condition_score": 88, "is_new_registration": False}
    mapped2 = FingerprintMatchResponse.model_validate(legacy_fingerprint_mapper(raw2))
    assert mapped2.is_match is True
    assert mapped2.matched_asset_id == "AS-000031"
    assert mapped2.similarity >= 0.75


def test_intent_legacy_label_key():
    raw = {"intent": "size_uncertain", "score": 1.4, "reasons": ["사이즈표 반복 조회"]}
    mapped = IntentClassifyResponse.model_validate(legacy_intent_mapper(raw))
    assert mapped.hesitation_type.value == "SIZE_UNCERTAIN"
    assert mapped.confidence == 1.0  # 범위 밖 값은 잘라낸다
    assert mapped.signals[0].evidence == "사이즈표 반복 조회"


def test_intent_legacy_unknown_label_falls_back_to_none():
    mapped = IntentClassifyResponse.model_validate(legacy_intent_mapper({"label": "무엇"}))
    assert mapped.hesitation_type.value == "NONE"
