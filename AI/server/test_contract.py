"""노트북 셀 5-6·5-7 의 검증을 그대로 재현 — 승격된 로직이 노트북과 동일함을 보증.

실행: 이 디렉토리에서 `python -m pytest test_contract.py -q`
(레포 루트 pytest 수집 범위(tests/) 밖의 독립 테스트다 — AI1 파트 소유.)
"""

from intent_logic import HESITATION_TYPES, predict_intent

# 셀 5-6 — 계약 예시(contracts/examples/intent_classify.request.json)와 완전 일치
EXAMPLE_REQUEST = {
    "customer_id": "CU-0007",
    "session_events": [
        {"event_type": "view_product", "product_id": "LX-0012",
         "timestamp": "2026-08-14T10:02:11+09:00", "dwell_seconds": 42.0, "meta": {}},
        {"event_type": "size_guide", "product_id": "LX-0012",
         "timestamp": "2026-08-14T10:03:20+09:00", "dwell_seconds": 88.5, "meta": {"size": "38"}},
        {"event_type": "size_guide", "product_id": "LX-0012",
         "timestamp": "2026-08-14T10:05:02+09:00", "dwell_seconds": 61.0, "meta": {"size": "38.5"}},
        {"event_type": "add_to_cart", "product_id": "LX-0012",
         "timestamp": "2026-08-14T10:06:40+09:00", "dwell_seconds": 5.0, "meta": {}},
    ],
}

EXPECTED = {
    "hesitation_type": "SIZE_UNCERTAIN",
    "confidence": 0.82,
    "signals": [
        {"name": "size_guide_repeat", "weight": 0.62, "evidence": "size_guide 2회 조회 (38, 38.5)"},
        {"name": "cart_without_checkout", "weight": 0.2, "evidence": "장바구니 담기 후 결제 진입 없음"},
    ],
}


def test_contract_example_exact_match():
    assert predict_intent(EXAMPLE_REQUEST) == EXPECTED


# 셀 5-7 — 라벨 5종 + 예외 미발생
EXTRA_CASES = [
    ("CU-0101", "STOCK_CONCERN", [
        {"event_type": "view_product", "product_id": "AA-01",
         "timestamp": "2026-08-14T10:00:00+09:00", "dwell_seconds": 20.0, "meta": {}},
        {"event_type": "stock_check", "product_id": "AA-01",
         "timestamp": "2026-08-14T10:01:00+09:00", "dwell_seconds": 3.0, "meta": {}},
    ]),
    ("CU-0102", "NONE", [
        {"event_type": "view_product", "product_id": "BB-02",
         "timestamp": "2026-08-14T10:00:00+09:00", "dwell_seconds": 4.0, "meta": {}},
    ]),
    ("CU-0103", "STYLE_DOUBT", [
        {"event_type": "view_product", "product_id": f"CC-{i:02d}",
         "timestamp": "2026-08-14T10:00:00+09:00", "dwell_seconds": 10.0, "meta": {}}
        for i in range(4)
    ]),
    ("CU-0104", "PRICE_HESITANT", [
        {"event_type": "price_filter_change", "product_id": None,
         "timestamp": "2026-08-14T10:00:00+09:00", "dwell_seconds": 0.0,
         "meta": {"max_price_krw": 5000000}},
        {"event_type": "price_filter_change", "product_id": None,
         "timestamp": "2026-08-14T10:01:00+09:00", "dwell_seconds": 0.0,
         "meta": {"max_price_krw": 3000000}},
    ]),
    ("CU-0105", "NONE", [
        {"event_type": "view_product", "product_id": "ZZ-1",
         "timestamp": "2026-08-14T10:00:00+09:00", "dwell_seconds": 10.0, "meta": {}},
        {"event_type": "add_to_cart", "product_id": "ZZ-1",
         "timestamp": "2026-08-14T10:01:00+09:00", "dwell_seconds": 5.0, "meta": {}},
        {"event_type": "purchase", "product_id": "ZZ-1",
         "timestamp": "2026-08-14T10:02:00+09:00", "dwell_seconds": 5.0, "meta": {}},
    ]),
]


def test_extra_cases_labels_and_no_exceptions():
    for customer_id, expected_label, events in EXTRA_CASES:
        result = predict_intent({"customer_id": customer_id, "session_events": events})
        assert result["hesitation_type"] == expected_label, (customer_id, result)
        assert result["hesitation_type"] in HESITATION_TYPES
