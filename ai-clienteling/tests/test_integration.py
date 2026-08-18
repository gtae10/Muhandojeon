# 통합 레이어 연동 테스트 — /api/chat 폴백 1회 + /clienteling/reply 2회 (LLM 3회 호출)
#
# 확인하는 것
#   1. 폴백 경로가 legacy 형식을 받아 답한다
#   2. 케어 요청 턴: 자산이 인용되고(cited_asset_ids) cta 가 저쪽 enum 으로 나간다
#      문장에는 점수·시스템 ID 가 없다 (진단서 화법 방지)
#   3. 사이즈 문의 턴: 인용이 비어 있다 (카드 시점 게이트 —
#      우리가 실루엣 등으로 보유 제품을 언급해도 케어 화제 전에는 카드를 띄우지 않는다)
#
# 실행: python tests/test_integration.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api import app

client = TestClient(app)

OWNED_ASSET = {
    "asset_id": "AS-0001",
    "customer_id": "CU-0007",
    "product_id": "P003",  # 실제 카탈로그의 Liz 비세토스 리버서블 쇼퍼
    "product_name": "Liz 비세토스 리버서블 쇼퍼",
    "purchased_at": "2023-05-01T00:00:00+09:00",
    "condition_score": 71,  # 입구에서 버려져야 한다 — 문장에 나오면 실패
    "findings": [{"part": "handle", "severity": "MEDIUM", "note": "핸들 마모 진행"}],
    "next_service_months": 2,
}

# ── 1. 폴백 경로 /api/chat (통합 레이어의 legacy_payload 형식 그대로) ──
r1 = client.post("/api/chat", json={
    "session_id": "CU-0007",
    "message": "노트북이 들어갈까요?",
    "product_id": "LX-0012",
    "history": [{"role": "customer", "content": "노트북이 들어갈까요?"}],
})
print("=== /api/chat", r1.status_code, "===")
print(json.dumps(r1.json(), ensure_ascii=False, indent=2))

# ── 2. 계약 경로: 고객이 자기 쇼퍼를 종류로 부르며 케어를 요청 → 인용되어야 함 ──
r2 = client.post("/clienteling/reply", json={
    "customer_id": "CU-0007",
    "hesitation_type": "NONE",
    "owned_assets": [OWNED_ASSET],
    "strategy_id": "S2",
    "history": [
        {"role": "customer", "content": "가지고 있는 쇼퍼백이 요즘 좀 낡은 것 같아서요. 손질을 받을 수 있나요?"}
    ],
})
print("=== /clienteling/reply (케어 요청)", r2.status_code, "===")
print(json.dumps(r2.json(), ensure_ascii=False, indent=2))

# ── 3. 계약 경로: 사이즈 문의 (고객은 쇼퍼를 언급 안 함) → 인용되면 안 됨 ──
r3 = client.post("/clienteling/reply", json={
    "customer_id": "CU-0007",
    "hesitation_type": "SIZE_UNCERTAIN",
    "owned_assets": [OWNED_ASSET],
    "strategy_id": "S2",
    "history": [
        {"role": "customer", "content": "Aren 스쿨 토트에 노트북이 들어갈까요?"}
    ],
})
print("=== /clienteling/reply (사이즈 문의)", r3.status_code, "===")
print(json.dumps(r3.json(), ensure_ascii=False, indent=2))

# 판정 — 사람이 다시 읽지 않아도 되게 핵심만 검사
b2, b3 = r2.json(), r3.json()
checks = {
    "폴백 경로 200 + reply 있음": r1.status_code == 200 and bool(r1.json().get("reply")),
    "케어 턴: 인용에 AS-0001": "AS-0001" in b2.get("cited_asset_ids", []),
    "케어 턴: 답변이 쇼퍼 이야기": ("Liz" in b2.get("message", "")) or ("쇼퍼" in b2.get("message", "")),
    "케어 턴: 문장에 점수(71)·AS- 없음": "71" not in b2.get("message", "") and "AS-" not in b2.get("message", ""),
    "케어 턴: cta 가 저쪽 enum 값": b2.get("cta") in {"BOOK_FITTING", "VIEW_STOCK", "CARE_BOOKING", "NONE"},
    "사이즈 턴: 인용 없음 (카드 시점 게이트)": b3.get("cited_asset_ids", []) == [],
}
print("=== 판정 ===")
failed = 0
for label, ok in checks.items():
    print(("O " if ok else "X "), label)
    failed += 0 if ok else 1
sys.exit(1 if failed else 0)
