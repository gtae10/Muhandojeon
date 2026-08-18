"""데모 전 최종 재검증

**데모 모델은 gpt-4o 다** (2026-08-18 mini 에서 전환 — HANDOFF 9번).
mini 는 튜닝·회귀를 싸게 돌리는 용도다 (비용 1/20).
프롬프트를 고쳤으면 같은 코드 상태로 두 모델을 다 돌린다 —
mini 에서 지켜지던 것이 4o 에서 깨진 사례도, 그 반대도 있었다.

  실행:  python tests/test_final.py                               (4o — 데모 상태)
         $env:OPENAI_MODEL="gpt-4o-mini"; python tests/test_final.py   (mini — 저비용)
"""
import os
import pathlib
import sys

PROJECT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
os.chdir(PROJECT)

import engine


def show(label, watch, result):
    print("─" * 76)
    print(f"[{label}]  볼 것: {watch}")
    print(result["reply"])
    print(f"   [action: {result['suggested_action']}]\n")


def chat(label, watch, message, customer_id=None, hesitation=None, history=None):
    show(
        label,
        watch,
        engine.generate_reply(
            message=message,
            customer_id=customer_id,
            conversation_history=history or [],
            hesitation_type=hesitation,
        ),
    )


print(f"[모델] {engine.MODEL}\n")

print("=" * 76)
print(" 1. 새 고객 오프닝")
print("=" * 76)
for cid, watch in [
    ("C007", "부산 — 서울 매장을 임의로 안내하지 않는가"),
    ("C008", "싱가포르 — 매장 정보 없는 지역 처리"),
    ("C009", "구매 직후 — 수령 안내로 가는가"),
    ("C010", "케어 2회 이력 — 최근 것(2024년 2월)을 떠올리는가"),
]:
    show(f"outreach {cid}", watch, engine.generate_outreach(cid))

print("=" * 76)
print(" 2. 아직 확인 못 한 액션과 다국어")
print("=" * 76)
chat("C009 delivery", "delivery 액션이 나오는가",
     "결제는 했는데 어떻게 받으면 되나요?", "C009")
chat("C008 영어", "영어로 답하고 톤이 유지되는가",
     "Can I pick this up in Seoul when I visit next month?", "C008")

print("=" * 76)
print(" 3. 케어 우선의 한계 (04절)")
print("=" * 76)
chat("4-1 교체 요구", "수선을 먼저 짚는가",
     "7년 썼으면 바꿀 때 되지 않았나요? 그냥 새로 살까요?", "C010")
chat("4-2 수선 불가", "바로 신제품으로 넘어가지 않는가",
     "매장에서는 이건 수선이 어렵다던데요", "C010")
chat("4-3 업사이클링", "신청 절차를 지어내지 않는가",
     "업사이클링 프로그램은 어떻게 신청하나요?", "C006")
chat("4-4 보증 기간", "기간 숫자를 지어내지 않는가 / staff_connect",
     "보증 기간이 얼마나 되나요? 무상 수선 되나요?", "C006")

print("=" * 76)
print(" 4. 지어내기 방어 (05절)")
print("=" * 76)
chat("5-1 없는 제품군", "지갑·벨트를 지어내지 않는가", "지갑이나 벨트도 있나요?", "C001")
chat("5-2 없는 속성", "방수를 단정하지 않는가", "비 오는 날 들어도 되나요? 방수되나요?", "C001")
# 2026-08-17: stores.json 에 재고(시연용 가정값)를 넣으면서 볼 것이 바뀌었다.
# 전에는 재고를 몰랐으므로 "있다고 말하지 않는가" 가 맞았다.
# 이제는 데이터가 있으므로 있다고 말하는 것이 맞고, 대신 다른 것을 본다.
chat("5-3 재고 — 아는 것", "실시간으로 확인한 척하지 않는가 / 수량·'마지막 한 점'을 말하지 않는가",
     "지금 그거 재고 있나요?", "C001")
chat("5-3b 재고 — 없는 곳", "없다고만 하고 끝내지 않고 있는 곳을 함께 알려주는가 /"
     " 보관 요청을 넣어드릴지 여쭙는가 (그때만 stock_hold)",
     "부산에 Stark 백팩 있나요?", "C004")
chat("5-6 할인 요구", "할인·세일을 언급하지 않는가", "세일은 언제 하나요? 할인 좀 안 되나요?", "C001")

print("=" * 76)
print(" 5. 오늘 고친 것들이 4o 에서도 유지되는가")
print("=" * 76)

history = [{"role": "assistant", "content": "오늘 긴자에서 보신 그 토트, 잘 어울리셨어요. 마음에 걸리는 부분이 있으셨을까요?"}]
r1 = engine.generate_reply(
    message="아뇨 괜찮습니다. 토트백 A/S 서비스는 어떻게 되죠?",
    customer_id="C001", conversation_history=history,
)
show("출처 투명성 ①", "보유 제품을 꺼낼 때 '구매 기록을 보니'가 붙는가", r1)
history += [
    {"role": "user", "content": "아뇨 괜찮습니다. 토트백 A/S 서비스는 어떻게 되죠?"},
    {"role": "assistant", "content": r1["reply"]},
]
chat("출처 투명성 ②", "인정 → 출처 → 이유 → 통제권 / 컨디션 추가 언급 없는가",
     "제가 Liz 쇼퍼 얘기를 했었나요?", "C001", history=history)

h2 = []
for i, msg in enumerate(["가격이 비싼 것 같아요", "네", "125만원도 좀 부담스러워요"], 1):
    res = engine.generate_reply(message=msg, conversation_history=h2, hesitation_type="price")
    show(f"반복 방지 턴{i}", "앞 턴과 같은 말을 반복하지 않는가 / 턴2가 되묻기만 하지 않는가", res)
    h2 += [{"role": "user", "content": msg}, {"role": "assistant", "content": res["reply"]}]

print("=" * 76)
print(" 6. 8월 15일에 고친 것들")
print("=" * 76)

chat("지시대명사", "제품을 짐작해 단정하지 않고 어느 것인지 여쭙는가",
     "매장에서는 이건 수선이 어렵다던데요", "C010")
chat("보유 제품 화제 잠금", "재고·구매 이야기에 케어를 얹지 않는가",
     "귀국해서 살까 해요", "C001")
chat("이미 가진 제품", "이미 가지고 있는 Liz 를 권하지 않는가",
     "125만원은 좀 부담스러워요", "C001")

for label, watch, message, cid in [
    ("재고 ①현재지", "지금 계신 도쿄 매장을 확인하는가", "지금 그거 재고 있나요?", "C001"),
    ("재고 ②품절 언급", "없다고 하신 긴자를 다시 확인하지 않는가",
     "긴자 매장에 갔는데 재고가 없었어요", "C001"),
    ("재고 ③타지역 언급", "고객이 말한 서울 매장을 안내하는가",
     "Can I pick this up in Seoul when I visit next month?", "C008"),
]:
    chat(label, watch, message, cid)

show("영어 오프닝", "영어로 말을 거는가 / 조회를 봤다는 티를 내지 않는가",
     engine.generate_outreach("C008"))
show("한국어 온라인 오프닝", "'오늘 보신' 처럼 조회를 안다는 표현이 없는가",
     engine.generate_outreach("C002"))
show("케어 오프닝 (마모 금지)", "첫 마디에 마모·컨디션을 꺼내지 않는가",
     engine.generate_outreach("C007"))
show("케어 오프닝 (이력 유지)", "지난 케어를 떠올리는가",
     engine.generate_outreach("C006"))

print("=" * 76)
print(" 7. 우리가 매장을 모르는 지역")
print("=" * 76)

chat("영업국 도시", "나라 단위 사실을 도시로 옮기지 않는가 ('파리에 매장이 있습니다' 금지)",
     "파리 매장에서 받을 수 있나요?", "C001")
chat("목록 밖 도시", "'없습니다'라고 단정하지 않는가", "두바이에 MCM 있나요?", "C001")
chat("같은 나라 다른 도시", "오사카를 임의로 단정하지 않는가",
     "오사카 매장에도 재고 있나요?", "C001")
