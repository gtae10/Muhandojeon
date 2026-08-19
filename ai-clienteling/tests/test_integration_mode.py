# 통합 경로(/clienteling/reply) 테스트 — "한 메종" 세계관 (LLM 8회)
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
#   7. 피팅 여쭘에 수락하면 cta 가 붙는다 (BOOK_FITTING 승격 — 2026-08-19)
#   8. 거절 턴에는 BOOK_FITTING 이 절대 안 붙는다 (오탐 0 원칙)
#   +. 승격 게이트 단위 검사 (LLM 0회 — 프로브 실측 문장 기준)
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

# --- BOOK_FITTING 승격 (2026-08-19) ---
# 피팅 여쭘 뒤 수락 → 카드가 붙어야 한다. 엔진이 care_booking 으로 분류하는
# 실행도 있어(주로 mini) CARE_BOOKING 도 정합으로 본다 — NONE 만 실패다.
FITTING_ASK = {
    "role": "agent",
    "content": "평소 240을 신으신다면 38이 가장 가깝지만, 더비는 발볼에 따라 "
               "착화감이 달라 매장에서 직접 신어보시는 것이 정확합니다. "
               "피팅 예약을 도와드릴까요?",
}
size_q = turn("Aurelia Derby를 보고 있는데 평소 240을 신어요. 38이 맞을까요?")

b = call([size_q, FITTING_ASK, turn("네, 그렇게 해주세요.")], hesitation="SIZE_UNCERTAIN")
results["7 피팅 여쭘 수락 → 카드 (BOOK_FITTING/CARE_BOOKING)"] = b["cta"] in {
    "BOOK_FITTING", "CARE_BOOKING"}
print("[7]", f"cta={b['cta']}", b["message"], "\n")

b = call([size_q, FITTING_ASK, turn("아니요, 괜찮아요. 다음에 할게요.")],
         hesitation="SIZE_UNCERTAIN")
results["8 피팅 거절 → BOOK_FITTING 없음 (오탐 0)"] = b["cta"] != "BOOK_FITTING"
print("[8]", f"cta={b['cta']}", b["message"], "\n")

# --- 승격 게이트 단위 검사 (LLM 0회) ---
# 프로브(mini·4o × 장면 2 × 3회)에서 수집한 실제 문장이 기준이다.
from api import _book_fitting_cta  # noqa: E402

HIST_ASK = [{"role": "assistant", "content": FITTING_ASK["content"]}]
gate_cases = [
    ("g1 확정형 (피팅 예약을 진행하겠습니다)", True,
     "Aurelia Derby의 피팅 예약을 진행하겠습니다.", "네, 그렇게 해주세요.", HIST_ASK),
    ("g2 여쭘형 (실착 경험을 도와드릴까요)", True,
     "38이 적합할 가능성이 큽니다. 매장에서 실착 경험을 도와드릴까요?", "38이 맞을까요?", []),
    ("g3 수락 연속 (답변에 피팅 단어 없음)", True,
     "접수를 넣어드리겠습니다. 매장에서 확인 후 연락드리겠습니다.",
     "네, 그렇게 해주세요.", HIST_ASK),
    ("g4 권유형은 제외 (신어보시는 것을 권장합니다)", False,
     "가까운 매장에서 직접 신어보시는 것을 권장합니다. 그 지역 매장은 제가 확인해드릴까요?",
     "38이 맞을까요?", []),
    ("g5 문장 분리 (착용 권유 + 재고 확인 여쭘)", False,
     "매장에서 직접 착용해보시고 편한 사이즈를 선택하시는 것이 가장 좋습니다. "
     "매장에 확인 요청을 넣어드릴까요?", "38이 맞을까요?", []),
    ("g6 거절 차단 (거절 후 상시 제안)", False,
     "알겠습니다. 원하시면 언제든 피팅 예약을 도와드리겠습니다.",
     "아니요, 다음에 할게요.", HIST_ASK),
    ("g7 수선 접수는 피팅 아님", False,
     "핸들 마모는 보습 관리를 권해드립니다. 수선 접수를 도와드릴까요?",
     "관리 어떻게 해요?", []),
]
for label, expected, reply, msg, hist in gate_cases:
    results[label] = _book_fitting_cta(reply, msg, hist) == expected

# --- 근거 카드(인용) 게이트 단위 검사 (LLM 0회) — 2026-08-19 손 테스트 사고 2건 ---
from api import _asset_in_text, _cited_asset_ids  # noqa: E402

DERBY = {"asset_id": "AS-0010", "product_name": "Aurelia Derby"}
CU3_OWNED = [DERBY, {"asset_id": "AS-0011", "product_name": "Vesper Ankle Boot"}]
results["c1 Oxford 발화가 보유 Derby 토큰에 안 걸림 (카탈로그 이름 소속)"] = not _asset_in_text(
    DERBY, "장바구니에 담아둔 Aurelia Oxford, 평소 240을 신는데 38이 맞을까요?", CU3_OWNED)
results["c2 Derby 전체 이름·단독 토큰은 걸림"] = _asset_in_text(
    DERBY, "제 Aurelia Derby 앞창이 닳았어요", CU3_OWNED) and _asset_in_text(
    DERBY, "제 Derby 상태 좀 봐주세요", CU3_OWNED)
results["c3 새로 사려는 사이즈 문의(비케어)에 인용 없음"] = _cited_asset_ids(
    "Aurelia Derby는 38 사이즈가 적합할 것입니다.",
    "Aurelia Derby를 보고 있는데 평소 240을 신어요. 38이 맞을까요?",
    "staff_connect", CU3_OWNED) == []
results["c4 같은 자산이라도 케어 턴이면 인용"] = _cited_asset_ids(
    "Aurelia Derby 앞창 케어 접수를 도와드리겠습니다.",
    "제 Aurelia Derby 앞창이 닳았는데 봐주실 수 있나요?",
    "care_booking", CU3_OWNED) == ["AS-0010"]
results["c5 연속(앞 턴에 꺼낸 자산) 유지"] = _cited_asset_ids(
    "Aurelia Derby 케어는 보습 위주로 진행됩니다.", "네", "none", CU3_OWNED,
    past_advisor_text="Aurelia Derby 점검을 도와드릴까요?") == ["AS-0010"]
results["c6 화제가 케어를 떠난 연속 턴 → 카드 내려감"] = _cited_asset_ids(
    "Aurelia Derby는 이미 보유하고 계시니, 어떤 용도의 가방을 찾고 계신가요?",
    "다른 가방을 살까 고민 중이에요", "none", CU3_OWNED,
    past_advisor_text="Aurelia Derby 점검을 도와드릴까요?") == []
# 손 테스트 실측 답변 (2026-08-19) — "살펴보시는"(제품 구경)이 케어 어휘
# "살펴"에 걸려 구매 턴에 카드가 남았던 사고. "살펴드"로 좁혀 해결.
results["c7 '살펴보시는'(구경)은 케어 어휘 아님 → 카드 내려감"] = _cited_asset_ids(
    "새로 구매를 고려 중이라면, 다른 라인을 살펴보시는 것도 좋겠습니다. "
    "이미 가지고 계신 Aurelia Derby는 대형입니다. 어떤 용도를 찾으시나요?",
    "새로 살까 고민 중이에요", "none", CU3_OWNED,
    past_advisor_text="Aurelia Derby 점검을 도와드릴까요?") == []
results["c8 '살펴드릴까요'(케어)는 유지"] = _cited_asset_ids(
    "Aurelia Derby를 한번 살펴드릴까요? 상태 확인 후 안내드리겠습니다.",
    "네", "none", CU3_OWNED,
    past_advisor_text="Aurelia Derby 점검을 도와드릴까요?") == ["AS-0010"]

print("=== 판정 ===")
failed = 0
for label, ok in results.items():
    print(("O " if ok else "X "), label)
    failed += 0 if ok else 1
sys.exit(1 if failed else 0)
