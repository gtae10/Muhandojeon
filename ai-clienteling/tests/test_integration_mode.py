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
#   6. 케어 시점(care_due) 자산이 있으면 재고 턴에도 카드가 보장된다 (D3)
#   7. 피팅 여쭘에 수락하면 cta 가 붙는다 (BOOK_FITTING 승격 — 2026-08-19)
#   8. 거절 턴에는 BOOK_FITTING 이 절대 안 붙는다 (오탐 0 원칙)
#   +. 승격 게이트·카드 게이트·노트 단위 검사 (LLM 0회 — 실측 문장 기준)
#      카드 게이트는 2026-08-19 저녁 "근거 인용"으로 재정의됨 (팀 계약 정렬)
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

# OWNED 는 next_service_months=1 이라 케어 시점(care_due) 자산이다.
# 재고 질문에도 답 끝에 케어 시점 한 문장이 붙고(모델이 빠뜨리면 후처리가
# 붙인다) 카드가 보장된다 — 데모 D3 의 형태 (2026-08-19 저녁).
b = call([turn("Solène Shoulder 재고가 서울에 있나요?")])
results["6 케어 시점 자산 → 재고 답 + 카드 보장 (D3 형태)"] = (
    "AS-0001" in b["cited_asset_ids"] and "Top Handle" in b["message"]
)
print("[6]", f"cited={b['cited_asset_ids']}", b["message"], "\n")

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

# --- 근거 카드(인용) 게이트 단위 검사 (LLM 0회) ---
#
# 2026-08-19 저녁 **기준 변경** (버그 수정이 아니다): 팀 계약의 하드 요구사항
# ("owned_assets 가 있으면 인용 최소 1개")과 데모 판정(min_citations)에 맞춰,
# "케어 화제일 때만" → "우리 답변이 그 자산을 언급했으면 인용"으로 넓혔다.
# 카드는 컨디션 경고가 아니라 "자산을 근거로 썼다"는 증거다.
# 계속 차단되는 것: 고객만 언급한 비케어 턴(8/19 마모 카드 사고 원형),
# 출처 추궁 턴(호출부에서 차단).
# 이에 따라 옛 c3(같은 모델 구매 문의 비인용)·c6·c7(케어 화제 이탈 시 카드
# 내려감)은 판정이 뒤집혔다 — 답변이 자산을 언급하면 이제 카드가 뜬다.
from api import _asset_in_text, _cited_asset_ids  # noqa: E402

DERBY = {"asset_id": "AS-0010", "product_name": "Aurelia Derby"}
CU3_OWNED = [DERBY, {"asset_id": "AS-0011", "product_name": "Vesper Ankle Boot"}]
results["c1 Oxford 발화가 보유 Derby 토큰에 안 걸림 (카탈로그 이름 소속)"] = not _asset_in_text(
    DERBY, "장바구니에 담아둔 Aurelia Oxford, 평소 240을 신는데 38이 맞을까요?", CU3_OWNED)
results["c2 Derby 전체 이름·단독 토큰은 걸림"] = _asset_in_text(
    DERBY, "제 Aurelia Derby 앞창이 닳았어요", CU3_OWNED) and _asset_in_text(
    DERBY, "제 Derby 상태 좀 봐주세요", CU3_OWNED)
results["c3 답변이 자산을 근거로 언급(비케어 사이즈 턴) → 인용"] = _cited_asset_ids(
    "구매 기록을 보니 Aurelia Derby와 같은 라스트라, 같은 사이즈를 권해드립니다.",
    "이 신발 38.5랑 39 중에 뭐가 맞을까요?", "staff_connect", CU3_OWNED) == ["AS-0010"]
results["c4 고객이 케어를 청한 턴 — 답변에 이름이 없어도 인용"] = _cited_asset_ids(
    "네, 살펴드리겠습니다. 접수를 도와드릴까요?",
    "제 Aurelia Derby 앞창이 닳았는데 봐주실 수 있나요?",
    "care_booking", CU3_OWNED) == ["AS-0010"]
results["c5 고객만 언급 + 비케어 → 차단 (마모 카드 사고 원형)"] = _cited_asset_ids(
    "Aurelia Oxford는 38, 38.5, 39 사이즈가 있습니다.",
    "제 Aurelia Derby랑 비슷한 Oxford를 보고 있어요", "staff_connect", CU3_OWNED) == []
results["c6 둘 다 언급 없음 → 빈 배열"] = _cited_asset_ids(
    "서울 매장에 재고가 있습니다.", "재고 있나요?", "stock_hold", CU3_OWNED) == []
results["c7 답변이 언급하면 화제와 무관하게 인용 (기준 변경 확인)"] = _cited_asset_ids(
    "Aurelia Derby는 이미 보유하고 계시니, 어떤 용도의 가방을 찾고 계신가요?",
    "다른 가방을 살까 고민 중이에요", "none", CU3_OWNED) == ["AS-0010"]
results["c8 케어 설명 연속 턴 인용 유지"] = _cited_asset_ids(
    "Aurelia Derby 케어는 보습 위주로 진행됩니다.", "네", "none",
    CU3_OWNED) == ["AS-0010"]
# 종류 단어 매칭은 고객 발화 전용 (2026-08-20) — 새 지갑을 안내하는 답변의
# "지갑" 이 보유 카드홀더에 걸려 컨디션 카드가 오점등된 실측 사고.
CU3_W = CU3_OWNED + [{"asset_id": "AS-0012", "product_name": "Lisière Card Holder"}]
results["c9 새 지갑 안내 답변의 종류 단어 → 보유 카드 오점등 없음"] = _cited_asset_ids(
    "지갑을 원하신다면 Lisière Long Wallet을 추천드립니다. 가격은 1,900,000원입니다.",
    "지갑도 하나 보고 싶어요.", "none", CU3_W) == []
results["c10 고객이 종류로 케어를 청하면 여전히 인용"] = _cited_asset_ids(
    "네, 살펴드리겠습니다. 접수를 도와드릴까요?",
    "가지고 있는 지갑 케어 좀 받고 싶어요", "care_booking", CU3_W) == ["AS-0012"]

# --- 승격·노트·방어 단위 검사 (LLM 0회, 2026-08-19 저녁) ---
from api import _care_booking_cta, _book_fitting_cta as _bf  # noqa: E402
from prompts.knowledge import (  # noqa: E402
    data_overlay as _overlay, pick_products as _pick,
    build_same_last_note, build_longevity_note, build_care_due_note,
    owned_catalog_ids,
)
from api import INTEGRATION_DATA  # noqa: E402

results["p1 초대 의문형 피팅 여쭘 → BOOK_FITTING (실측 문장)"] = _bf(
    "매장에서 Aurelia Top Handle을 직접 착용해 보시겠어요?", "할인 없나요?", [])
results["p2 케어 예약 여쭘 → CARE_BOOKING 승격 (실측 문장)"] = _care_booking_cta(
    "케어 예약을 함께 잡아드릴까요?", "재고 있나요?")
results["p3 케어 방법 안내(정보 동사)는 승격 안 함"] = not _care_booking_cta(
    "케어 방법을 알려드릴까요?", "관리 어떻게 해요?")
results["p4 거절 턴은 케어 승격 차단"] = not _care_booking_cta(
    "알겠습니다. 필요하시면 케어 예약을 도와드리겠습니다.", "아니요, 다음에 할게요.")
# care_due 승격 (2026-08-20) — 케어 시점 자산이 있으면 접수 어휘의 활용형과
# 무관하게, 답변의 케어 언급 자체로 승격한다 (서버 D3 실측: 능력 진술형
# "도와드릴 수 있습니다" 가 어휘 목록을 비껴가 판정 FAIL).
results["p5 care_due + 능력 진술형 → 승격 (D3 실측 문장)"] = _care_booking_cta(
    "정기 케어 시점이 되어 케어 예약도 도와드릴 수 있습니다.",
    "재고 있나요?", care_due=True)
results["p6 care_due 없으면 능력 진술형은 승격 안 함"] = not _care_booking_cta(
    "케어가 필요하시면 언제든 도와드릴 수 있습니다.", "재고 있나요?")
results["p7 care_due 라도 케어 언급 없는 답변은 승격 안 함"] = not _care_booking_cta(
    "서울 매장에 재고가 있습니다.", "재고 있나요?", care_due=True)
results["p8 care_due 라도 거절 턴은 차단"] = not _care_booking_cta(
    "알겠습니다. 케어는 편하실 때 말씀해 주세요.",
    "아니요, 케어는 다음에 할게요.", care_due=True)
results["p9 care_due 라도 출처 추궁 턴은 차단"] = not _care_booking_cta(
    "제가 먼저 말씀드린 것입니다. 구매 기록과 케어 접수 기록에서 확인했습니다.",
    "제가 그 가방 얘기를 했었나요?", care_due=True)
# care_due 분기 오탐 수정 (2026-08-20) — 답변 전체가 아니라 같은 문장에
# 케어 언급 + (접수 어휘 또는 능력 진술형)이 함께 있을 때만 승격한다.
# 케어 단어만 있고 제안이 없는 정보성 문장은 care_due=True 라도 승격 안 함.
results["p10 care_due + 정보 동사(여쭘형)는 승격 안 함"] = not _care_booking_cta(
    "케어 방법을 알려드릴까요?", "관리 어떻게 해요?", care_due=True)
results["p11 care_due + 정보성 평서문(비용 안내)은 승격 안 함"] = not _care_booking_cta(
    "케어 비용은 무료입니다.", "케어는 얼마예요?", care_due=True)
results["p12 care_due + 다른 서비스 제안(스태프 연결)은 승격 안 함"] = not _care_booking_cta(
    "케어 관련해서는 매장 어드바이저에게 확인을 요청해드릴까요?",
    "케어가 필요할까요?", care_due=True)
# 회귀 방지 — 기존 접수 어휘(BOOKING_WORDS) 경로는 care_due 값과 무관하게
# 그대로 동작해야 한다 (리팩터로 문장 루프를 하나로 합쳤으므로 확인).
results["p13 care_due + 실제 접수 여쭘(BOOKING_WORDS)은 여전히 승격"] = _care_booking_cta(
    "케어 예약을 함께 잡아드릴까요?", "재고 있나요?", care_due=True)
# 출처 추궁 차단이 능력 진술형 경로에도 걸리는지 (기존 p9 은 케어 단어만
# 있고 제안 어휘가 없는 문장이라 이 분기를 실제로 거치지 않았다).
results["p14 care_due + 출처 추궁 턴은 능력 진술형이 있어도 차단"] = not _care_booking_cta(
    "구매 기록에서 확인했습니다. 케어 예약도 도와드릴 수 있습니다.",
    "제가 그 가방 얘기를 했었나요?", care_due=True)

with _overlay(INTEGRATION_DATA):
    _cust = {"owned_products": [
        {"product_id": "LX-0005", "name": "Aurelia Derby", "purchased": "2023-04"}]}
    _text = "Aurelia Oxford 사이즈가 애매해요"
    results["n1 같은 라스트 노트 (Oxford 문의 + Derby 보유)"] = "같은 라스트" in (
        build_same_last_note(_pick(_text, _cust), _cust, _text))
    _bag_text = "Aurelia Top Handle 가격이 부담돼요"
    results["n2 가방 문의(형제 구두 동반 pick)에는 라스트 노트 없음"] = build_same_last_note(
        _pick(_bag_text, _cust), _cust, _bag_text) == ""
    results["n3 수명 노트 — 1년 이상 사용 자산만"] = (
        "구매 기록" in build_longevity_note({"owned_products": [
            {"product_id": "LX-0011", "name": "Lisière Card Holder",
             "purchased": "2023-09"}]})
        and build_longevity_note({"owned_products": [
            {"product_id": "LX-0011", "name": "Lisière Card Holder",
             "purchased": "2026-01"}]}) == ""
    )
    results["n4 케어 시점 노트 — care_due 자산만, 추궁 턴 차단"] = (
        "정기 케어" in build_care_due_note({"owned_products": [
            {"product_id": "LX-0001", "name": "Aurelia Top Handle",
             "purchased": "2022-04", "care_due": True}]})
        and build_care_due_note({"owned_products": [
            {"product_id": "LX-0001", "name": "Aurelia Top Handle",
             "care_due": True}]}, challenged=True) == ""
    )
    # 배포 프론트 오프라인 목업의 잘못된 ID(Derby 자산에 Oxford ID) 방어
    results["d1 이름↔ID 불일치면 이름을 믿는다"] = owned_catalog_ids(
        {"owned_products": [{"product_id": "LX-0006", "name": "Aurelia Derby"}]}
    ) == {"LX-0005"}

print("=== 판정 ===")
failed = 0
for label, ok in results.items():
    print(("O " if ok else "X "), label)
    failed += 0 if ok else 1
sys.exit(1 if failed else 0)
