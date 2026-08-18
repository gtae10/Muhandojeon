# 통합 경로(/clienteling/reply) 테스트 — "한 메종" 세계관 (LLM 6회)
#
# 2026-08-18 전면 개정: 통합 경로가 기존 MCM 엔진 + 데이터 오버레이(18종 카탈로그·
# 16명 고객·확장 재고)로 재설계됐다. 어드바이저는 전 제품·매장·재고·배송을 안다.
#
# 확인하는 것
#   1. fixture 제품(LX) 스펙을 소재·가격 사실로 답한다
#   2. MCM 제품을 소문자("liz")로 불러도 찾아서 매장 재고로 답한다
#   3. fixture 제품 재고를 매장 표로 답한다
#   4. 보유 LX 자산을 예산 대안으로 출처 없이 권하지 않는다
#   5. 출처 추궁 턴에는 인용(카드)이 비고 통제권 문장이 있다
#   6. 케어 화제가 아니면 인용이 빈다 (카드 시점 게이트)
#
# 실행: python tests/test_integration_mode.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api import app

client = TestClient(app)

# 팀 fixtures/assets.json 의 실제 자산 (CU-0001 한지원)
OWNED = {
    "asset_id": "AS-0001", "customer_id": "CU-0001", "product_id": "LX-0001",
    "product_name": "Aurelia Top Handle", "category": "BAG",
    "purchased_at": "2022-04-16T00:00:00+09:00", "condition_score": 71,
    "findings": [{"part": "handle", "severity": "MEDIUM", "note": "핸들 표면 마모 진행, 케어 임계 근접"}],
    "next_service_months": 1,
}


def call(history, hesitation="NONE", owned=True):
    r = client.post("/clienteling/reply", json={
        "customer_id": "CU-0001", "hesitation_type": hesitation,
        "owned_assets": [OWNED] if owned else [], "strategy_id": "S2",
        "history": history,
    })
    assert r.status_code == 200, r.text
    return r.json()


def turn(text):
    return {"role": "customer", "content": text}


results = {}

b = call([turn("Solène Shoulder는 어떤 가방이에요?")])
m = b["message"]
results["1 LX 스펙 (소재·가격 사실)"] = "Solène" in m and any(
    w in m for w in ("박스카프", "카프스킨", "6,400,000", "640만"))
print("[1]", m, "\n")

b = call([turn("liz를 사려고 하는데 서울에 재고가 있나요?")])
m = b["message"]
results["2 소문자 liz → MCM 재고 (매장 표)"] = "Liz" in m and "재고" in m and "Aren" not in m
print("[2]", m, "\n")

b = call([turn("Nocturne Clutch 재고가 서울에 있을까요?")])
m = b["message"]
results["3 LX 재고 (매장 표)"] = "Nocturne" in m and ("재고" in m or "매장" in m)
print("[3]", m, "\n")

b = call([turn("예산 1,000만원 정도로 백을 하나 보려고요.")])
m = b["message"]
# 보유(Aurelia Top Handle, 890만)가 예산 이내지만 출처 없이 대안으로 권하면 안 된다
results["4 보유 LX 예산 비권유"] = ("Top Handle" not in m) or ("구매 기록" in m)
print("[4]", m, "\n")

b = call([
    turn("백 관리를 어떻게 하면 좋을까요?"),
    {"role": "agent", "content": "구매 기록에 있는 Aurelia Top Handle의 핸들은 정기적인 보습 관리를 권해드립니다. 필요하시면 수선 접수를 도와드릴 수 있습니다."},
    turn("제가 그 백 얘기를 했었나요? 그걸 어떻게 아세요?"),
])
m = b["message"]
# 통제권 문장은 표현이 갈린다 ("원치 않으시면"/"원하지 않으시면") — 뜻으로 검사
results["5 추궁: 인용 차단 + 통제권"] = b["cited_asset_ids"] == [] and (
    "원치 않" in m or "원하지 않" in m or "원하시지 않" in m
)
print("[5]", m, "\n")

b = call([turn("노트북이 들어가는 백을 찾고 있어요.")])
results["6 케어 화제 아님 → 인용 없음 (카드 게이트)"] = b["cited_asset_ids"] == []
print("[6]", b["message"], "\n")

print("=== 판정 ===")
failed = 0
for label, ok in results.items():
    print(("O " if ok else "X "), label)
    failed += 0 if ok else 1
sys.exit(1 if failed else 0)
