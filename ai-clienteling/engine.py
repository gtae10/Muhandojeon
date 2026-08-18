"""
에이전트의 두뇌 — 상태를 갖지 않는 응답 생성기

콘솔(agent.py)과 API 서버(api.py)가 모두 이 파일을 쓴다.

왜 상태를 갖지 않는가:
API 서버는 여러 고객의 요청을 동시에 받는다. 전역 변수에 대화를 쌓아두면
A 고객의 대화에 B 고객의 말이 섞인다. 그래서 필요한 것을 전부 인자로 받고,
아무것도 기억하지 않는다. 대화 기록은 부르는 쪽이 관리한다.
"""

import json
import os
import sys
import time

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

from prompts.system_prompt import build_system_prompt
from prompts.knowledge import (
    load_customer,
    build_customer_block,
    build_outreach_instruction,
    pick_opening_material,
    build_hesitation_strategy,
    normalize_hesitation,
    normalize_purchased,
    fix_region_condition,
    LABEL_MAP,
    build_budget_note,
    build_constraints_note,
    build_owned_bridge,
    match_by_duration,
    build_continuity_note,
    build_no_repeat_note,
    build_language_note,
    extract_budget,
    extract_price_concern,
    hides_owned_detail,
    pick_products,
    build_product_detail,
    build_laptop_table,
    needs_laptop_table,
    build_extra_heritage,
    build_store_extra,
    build_stock_table,
    build_stock_decision,
    build_mentioned_region_note,
    build_place_note,
    build_source_challenge_note,
    needs_store_extra,
    build_unanswerable_note,
    build_unclear_note,
    CONDITION_TALK_HINTS,
    OWNED_TOPIC_HINTS,
)

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key.startswith("sk-여기에"):
    raise RuntimeError(".env 파일에 실제 OPENAI_API_KEY 가 없습니다.")

# 기본값 = 데모 모델. 아무것도 안 적으면 데모와 같은 환경이 된다.
#
# 2026-08-18 mini → 4o 전환. 8턴 스트레스에서 mini 는 직전 턴의 묻지 않은
# 제안에 다음 발화를 수락으로 삼켜 대화가 어긋났다(5회 중 2회). 4o 는 0회.
# 예선이 제출형이라 심사위원이 대화를 길게 밀 수 있어 장턴 품질을 우선했다.
# mini 는 튜닝·회귀용으로 계속 쓴다 (비용 1/20).
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
BASE_URL = os.getenv("OPENAI_BASE_URL") or None

client = OpenAI(api_key=api_key, base_url=BASE_URL)

# 팀 합의 스펙에 정의된 액션 값들.
VALID_ACTIONS = {"care_booking", "stock_hold", "delivery", "staff_connect", "none"}


# 답변을 JSON 으로 받기 위한 지시.
# 콘솔과 API가 똑같이 동작해야 테스트가 의미를 가지므로, 두 경로 모두 JSON 을 쓴다.
OUTPUT_FORMAT = """

# 출력 형식

아래 JSON 형식으로만 답합니다.

{"reply": "고객에게 보낼 말", "suggested_action": "액션값"}

reply 에는 고객에게 그대로 보일 문장만 담습니다. 형식 설명을 덧붙이지 않습니다.

**reply 를 비워두지 않습니다.** 무슨 말을 해야 할지 모르겠어도 빈 값을 보내지 않습니다.
고객이 "네" 처럼 짧게 답했다면 직전에 제안한 것을 이어서 설명합니다.

suggested_action 은 이번 답변에서 실제로 제안한 행동 하나입니다.
시스템이 뒤이어 처리할 일이 있을 때만 값을 넣습니다.

  care_booking   케어나 수선 접수를 도와드리겠다고 했을 때
  stock_hold     재고를 확인하거나 잡아두겠다고 했을 때
  delivery       구매한 제품을 어떻게 받을지 안내했을 때
                 (배송 방법, 어느 매장에서 픽업할지)
                 배송과 픽업 중 어느 쪽이 좋을지 여쭙는 형태여도 delivery 입니다.
                 고객이 답하면 시스템이 그 방법으로 처리해야 하기 때문입니다.
                 **이미 결제한 제품에만 씁니다.** 아직 사지 않은 제품을 두고
                 "귀국하시면 매장에서 찾으실 수 있어요" 라고 한 것은 delivery 가
                 아닙니다. 받을 물건이 아직 없습니다.
                 그 경우 재고를 확인하겠다고 했으면 stock_hold, 아니면 none 입니다.
  staff_connect  매장 어드바이저에게 확인을 요청하겠다고 했을 때
  none           위 어느 것도 아닐 때

**none 이 기본값입니다.** 애매하면 none 을 고릅니다.

자주 틀리는 경우
  "매장에서 실물을 보시는 것도 좋습니다"   → none 입니다. delivery 가 아닙니다.
                                            우리가 처리할 일이 없습니다.
  "전시가 열리고 있어 들르실 만합니다"     → none 입니다. 단순 안내입니다.
  질문만 하고 끝난 답변                    → none 입니다.

말로는 제안하지 않았는데 액션만 넣지 않습니다. 그 반대도 마찬가지입니다.
액션은 하나만 고릅니다.

"""


# 자주 놓치는 셋. 프롬프트 맨 뒤에 다시 붙인다.
#
# OUTPUT_FORMAT 은 system 안에 있어서 대화 기록과 턴별 블록들보다 앞에 놓인다.
# 오늘 블록을 여럿 추가하자 이 셋이 다시 묻히기 시작했다.
# (금지해둔 "언제든지 말씀해 주세요" 가 4o 에서 되살아났다)
# 모델은 가까이 있는 지시를 더 잘 따르므로 진짜 마지막 자리에 한 번 더 놓는다.
FINAL_CHECK = """
# 보내기 전 마지막 점검

앞의 규칙이 많지만, 그중 자주 놓치는 셋만 다시 확인합니다.

1. **빈 마무리를 붙이지 않았는가.**
   "더 궁금하신 점이 있으신가요?", "더 알고 싶으신가요?", "언제든 말씀해 주세요"
   → 전부 지웁니다. 덧붙일 말이 없으면 그냥 끝냅니다.
   구체적인 제안("접수를 도와드릴까요?")은 빈 마무리가 아니므로 괜찮습니다.

2. **앞 턴에서 한 말을 또 하지 않았는가.**
   같은 제품 설명, 같은 대안, 같은 매장 안내, 같은 되묻기를 두 번 하지 않습니다.
   묻지 않은 것을 매 턴 덧붙이지 않습니다.
   ("예산을 여쭤봐도 될까요?"를 세 턴 연속 붙인 적이 있습니다)

   **단, 고객이 새로 꺼낸 이야기에는 답합니다.**
   반복 금지는 덧붙임에 대한 것이지, 고객이 방금 말한 것을 무시하라는 뜻이 아닙니다.
   귀국·일정·수령을 처음 꺼냈다면 그것이 이번 턴의 용건입니다.

3. **여섯 문장을 넘지 않았는가.**
"""


# 프롬프트에 넣어도 되는 보유 제품 필드.
#
# 흘려보내지 않고 골라 받는 이유:
# 이 프로젝트에서 새어 나간 정보는 전부 "프롬프트에 있어서" 샜다.
# 모델은 눈앞에 있는 것을 결국 인용한다. 규칙으로 막는 것보다 안 보이는 편이 확실하다.
#
# 실제로 AI 1 은 condition_score(71), risk("핸들_마모_임계") 를 함께 보낸다.
# 그대로 두면 "컨디션 71점, 임계 근접" 같은 진단서 화법이 나온다.
# 우리가 금지 예시로 적어둔 바로 그 문장이다.
#
# 새 필드가 필요해지면 여기에 추가한다. 모르는 필드는 통과시키지 않는다.
OWNED_PRODUCT_FIELDS = ("product_id", "name", "purchased", "condition", "care_history")
CONDITION_FIELDS = ("overall", "notes")


def _clean_owned(products):
    """Backend·AI 1 이 보낸 보유 제품에서 우리가 쓰는 필드만 남긴다."""
    cleaned = []

    for product in products or []:
        if not isinstance(product, dict):
            continue

        # 이름이 없으면 이 제품에 대해 할 수 있는 말이 없다.
        # 그대로 두면 이름으로 대조하는 자리들이 None 을 만나 터진다.
        if not isinstance(product.get("name"), str) or not product["name"].strip():
            continue

        kept = {k: v for k, v in product.items() if k in OWNED_PRODUCT_FIELDS}

        # 구매 시점은 형식을 통일한다. Backend 가 무엇을 쓸지 우리가 정할 수 없다.
        # "2023/05/01" 은 ValueError, "2023" 은 IndexError 로 서버가 죽었다.
        # 못 읽으면 필드를 빼둔다 — 없으면 "구매 기록에 있는 X" 로 답이 나간다.
        if "purchased" in kept:
            canonical = normalize_purchased(kept["purchased"])
            if canonical:
                kept["purchased"] = canonical
            else:
                kept.pop("purchased")

        # condition 안에 점수 같은 것이 들어와도 같은 이유로 걸러낸다.
        condition = kept.get("condition")
        if isinstance(condition, dict):
            kept["condition"] = {
                k: v for k, v in condition.items() if k in CONDITION_FIELDS
            }
        elif "condition" in kept:
            # dict 가 아니면 우리가 읽는 모양이 아니다. 두면 그대로 프롬프트에 실린다.
            kept.pop("condition")

        # care_history 는 접수 기록의 목록이어야 한다.
        # 문자열로 오면 항목을 하나씩 훑는 자리에서 터진다.
        care = kept.get("care_history")
        if "care_history" in kept:
            if isinstance(care, list):
                kept["care_history"] = [c for c in care if isinstance(c, dict)]
            else:
                kept.pop("care_history")

        cleaned.append(kept)

    return cleaned


# Backend 가 쓸 법한 role 이름들. 뜻이 분명한 것만 옮긴다.
#
# 전부 버리면 대화 기록이 통째로 사라지는데 에러가 안 난다.
# 오늘 계속 찾아낸 "조용히 깨지는" 실패와 같은 종류다.
# 그렇다고 모르는 값을 아무 쪽으로 붙이면 더 나쁘다.
# 어드바이저가 한 말을 고객이 한 말로 잘못 붙이면 대화가 뒤집힌다.
ROLE_ALIASES = {
    "user": "user",
    "customer": "user",
    "human": "user",
    "고객": "user",
    "assistant": "assistant",
    "agent": "assistant",
    "advisor": "assistant",
    "bot": "assistant",
    "ai": "assistant",
    "어드바이저": "assistant",
}


VARIANTS = ("default", "storytelling", "practical", "control")


def _clean_text(value):
    """발화·ID 를 문자열로 맞춘다. 못 쓰는 값이면 빈 문자열.

    HTTP 로 오면 Pydantic 이 문자열을 보장하지만 직접 import 하면 아무거나 온다.
    숫자는 사람이 친 값일 수 있으니 문자열로 바꾸고("125"),
    리스트·딕셔너리는 사람이 친 말이 아니므로 버린다.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return ""


def _clean_variant(value):
    """모르는 응대 전략 버전은 default 로 본다.

    dict 키로 바로 쓰다가 리스트가 들어오면 unhashable 로 터졌다.
    """
    return value if value in VARIANTS else "default"


def _clean_history(history):
    """대화 기록에서 쓸 수 있는 것만 남긴다.

    HTTP 로 들어오면 Pydantic 이 형식을 지켜주지만, Backend 가 engine 을 직접
    import 하면 아무거나 들어온다. 실제로 content 가 None 이면 TypeError,
    키가 빠지면 KeyError, 항목이 문자열이면 AttributeError 로 죽었다.
    503개 조합을 태워보니 179개가 여기서 터졌다.

    system 은 별칭에 넣지 않는다.
    바깥에서 온 기록에 system 이 섞이면 우리 지침을 덮어쓰는 통로가 된다.

    버리는 것 자체는 문제가 아니다. **조용히** 버리는 것이 문제다.
    그래서 무엇을 왜 버렸는지 stderr 로 남긴다.
    Backend 가 role 이름을 다르게 쓰고 있으면 연동 첫날 바로 보인다.
    (stderr 이므로 고객 화면에는 안 나간다)
    """
    cleaned = []
    dropped = {}

    def note(reason):
        dropped[reason] = dropped.get(reason, 0) + 1

    for turn in history or []:
        if not isinstance(turn, dict):
            note(f"항목이 dict 가 아님({type(turn).__name__})")
            continue

        role = turn.get("role")
        mapped = ROLE_ALIASES.get(role.strip().lower()) if isinstance(role, str) else None
        if not mapped:
            note(f"role 을 알 수 없음({role!r})")
            continue

        content = turn.get("content")
        if not isinstance(content, str) or not content.strip():
            note("content 가 비었거나 문자열이 아님")
            continue

        cleaned.append({"role": mapped, "content": content})

    if dropped:
        detail = ", ".join(f"{why} {n}건" for why, n in dropped.items())
        print(
            f"[대화 기록] {sum(dropped.values())}개 턴을 버렸습니다. 사유: {detail}. "
            "role 은 user/assistant 로 보내주세요.",
            file=sys.stderr,
        )

    return cleaned


def build_customer(customer_id, owned_products=None):
    """고객 정보를 만든다.

    더미 데이터에 있는 고객이면 그것을 쓰고, 없으면 최소 정보로 만든다.
    Backend 가 owned_products 를 보내주면 그쪽을 우선한다.
    (실제 서비스에서는 CDP 가 보내주는 값이 우리 더미보다 정확하다)
    """
    if not customer_id:
        return None

    try:
        customer = load_customer(customer_id)
    except ValueError:
        customer = {"customer_id": customer_id, "owned_products": []}

    if owned_products is not None:
        customer = {**customer, "owned_products": _clean_owned(owned_products)}

    return customer


def derive_constraints(user_messages):
    """지금까지 고객이 한 말에서 예산 조건을 다시 뽑아낸다.

    상태를 갖지 않으므로, 매 요청마다 대화 기록을 훑어 조건을 재구성한다.
    """
    state = {"budget_max": None, "concerns": []}

    for text in user_messages:
        budget = extract_budget(text)
        if budget:
            state["budget_max"] = budget

        concern = extract_price_concern(text)
        if concern is not None and concern not in state["concerns"]:
            state["concerns"].append(concern)

    return state


# 출처를 밝혔다고 인정하는 표현들. 이것 없이 보유 제품을 꺼내면 감시로 읽힌다.
SOURCE_MARKS = (
    "구매 기록", "케어 접수 기록", "케어 기록", "접수 기록",
    # 영어 응답에서도 같은 규칙이 지켜져야 한다.
    # 한국어 표현만 보다 보니 영어에서는 검사가 아예 걸리지 않았고,
    # "your existing Stark backpack" 처럼 출처 없이 새어 나갔다.
    "purchase record", "purchase history", "care record", "service record",
)


def _unsourced_owned(reply, customer, talked):
    """출처 없이 보유 제품을 언급했는지 본다. 어겼으면 다시 요청할 문장을 만든다.

    고객이 직접 말한 제품은 대상이 아니다. 이미 화제에 올라 있으므로
    출처를 밝힐 이유가 없다. 우리가 먼저 꺼낸 경우만 본다.
    """
    if any(mark in reply for mark in SOURCE_MARKS):
        return ""

    for product in customer.get("owned_products") or []:
        name = product.get("name", "")
        if not name:
            continue
        line = name.split()[0]
        if line in reply and line not in talked:
            purchased = product.get("purchased")
            if purchased:
                year, month = purchased.split("-")[:2]
                phrase = f"구매 기록을 보니 {year}년 {int(month)}월에 들이신 {name}"
            else:
                phrase = f"구매 기록에 있는 {name}"
            return f"""
# 다시 씁니다 — 출처가 빠졌습니다

방금 답변에서 {line} 을(를) 언급했는데, 고객은 그 제품을 말한 적이 없습니다.
어디서 알았는지 밝히지 않으면 고객은 "그건 어떻게 아세요?" 부터 생각하게 됩니다.

그 부분을 아래 표현으로 바꿔서 답변 전체를 다시 씁니다.

  "{phrase}"

"현재 사용 중인", "갖고 계신", "2023년에 구매하신" 은 출처가 아닙니다.
우리가 어떻게 알았는지를 말해야 출처입니다.

**{line} 언급을 빼지 마십시오.** 빼는 것은 고치는 것이 아닙니다.
알고 있으면서 말하지 않으면 개인화의 기회를 버리는 것입니다.
언급은 그대로 두고 출처만 붙입니다.
나머지 내용과 길이도 그대로 두고 이 부분만 고칩니다."""

    return ""


def _recommended_owned(reply, customer, talked):
    """이미 가진 제품을 대안으로 권했는지 본다.

    예산 분류표와 제품 상세 양쪽에 "이미 보유" 표시를 넣었는데도
    "예산에 맞는 대안으로 Liz 쇼퍼가 있습니다" 가 세 번 다 나왔다.
    표시를 읽게 하는 것보다 결과를 검사하는 편이 확실하다.

    고객이 그 제품을 직접 말했거나, 우리가 출처를 밝히며 꺼낸 경우는 정상이다.
    권유 표현과 함께 나온 경우만 잡는다.
    """
    if any(mark in reply for mark in SOURCE_MARKS):
        return ""

    # 권유 표현 목록으로 걸렀더니 목록에 없는 표현으로 빠져나갔다.
    # ("예산을 우선하시면 Liz가 109만원인데 한 단계 작습니다")
    # 출처 없이 보유 제품 이름이 나온 것 자체가 문제이므로 조건을 단순하게 둔다.
    for product in customer.get("owned_products") or []:
        name = product.get("name", "")
        if not name:
            continue
        line = name.split()[0]
        if line in reply and line not in talked:
            return f"""
# 다시 씁니다 — 이미 가지고 계신 제품입니다

방금 답변에서 {name} 을(를) 대안으로 권했습니다.
이 고객이 이미 가지고 있는 제품입니다.

이미 가진 물건을 새로 권하는 것은 우리가 그 고객을 모른다는 뜻이 됩니다.
개인화를 내세우는 서비스에서 가장 하면 안 되는 실수입니다.

이 제품을 빼고 답변 전체를 다시 씁니다.
권할 만한 다른 제품이 없다면 억지로 권하지 말고,
어떤 조건을 우선하시는지 여쭙거나 지금 사지 않아도 되는 길을 엽니다."""

    return ""


def fix_delivery_action(result, customer):
    """delivery 는 이미 결제한 제품에만 쓴다.

    "귀국 후 픽업하시면 됩니다" 처럼 아직 사지 않은 제품의 수령 방법을 이야기할 때
    모델이 delivery 를 골랐다. 받을 물건이 아직 없으므로 틀린 값이다.
    Frontend 는 이 값으로 카드를 띄우므로 데모에서 어색해진다.

    프롬프트에 규칙을 적어두었지만 계속 샜다.
    구매 여부는 recent_activity 로 코드가 알 수 있으므로 여기서 정정한다.
    """
    if result.get("suggested_action") != "delivery":
        return result

    activity_type = (customer or {}).get("recent_activity", {}).get("type", "")
    if "구매 완료" in activity_type or "수령" in activity_type:
        return result

    # 결제한 적이 없다. 재고 확인을 제안했으면 stock_hold, 아니면 none.
    reply = result.get("reply", "")
    hinted = any(word in reply for word in ("재고", "확인해", "준비해", "잡아"))
    result["suggested_action"] = "stock_hold" if hinted else "none"
    return result


def pick_strategy(hesitation_type, from_ai1, state):
    """이번 턴에 어느 망설임 전략을 쓸지 정한다. (대화 중 = /chat 전용)

    ── AI 1 라벨은 대화 중에 전략을 고르지 않는다 (2026-08-18) ──

    AI 1 은 클릭 행동(세션)으로 분류한다. 고객이 채팅에서 한 마디도 하지 않아도
    값이 오고, 세션 단위라 매 턴 같은 값이 온다.
    그 값으로 전략을 붙이면 고객이 하지 않은 말을 우리가 확인해주게 된다.

      price   "가격이 마음에 걸리시는군요"  — 부담을 말한 적이 없다
      fit     치수·수납·무게를 쏟는다        — 사이즈를 물은 적이 없다
      timing  "서두르지 않으셔도 됩니다"     — 조급해한 적이 없다

    셋 다 "제가 그런 말을 했었나요?" 를 부르는 형태다. 출처 추궁과 같은 감시 문제다.

    전에는 price 에만 게이트를 두어 "고객이 가격을 말했는가"를 확인했다.
    계약이 바뀌어 fit(SIZE_UNCERTAIN)·timing(STOCK_CONCERN)도 오게 되자
    게이트를 셋으로 넓히려 했는데, 그 둘은 뽑아낼 숫자가 없어
    **발화의 화제를 단어로 맞혀야** 했다.
    만들어둔 목록이 첫 시험에서 "모레 귀국이라"(우리 대표 시나리오)를 놓쳤다.
    이 프로젝트에서 세 번째 실패다 — 목록은 목록 밖 표현으로 반드시 샌다.

    → 판정할 필요를 없앴다. 우리 문서가 이미 이 결론을 적어두고 있었다.
        · AI 1 = 대화 시작 전 세션 신호 (누구에게 언제 먼저 말 걸까) → /outreach
        · 대화 중 망설임 = 발화에서

    부르는 쪽이 우리 값(fit/price/timing/comparison)을 직접 넣은 것은 그대로 쓴다.
    그건 발화를 보고 정한 값이다.

    발화에서 고를 수 있는 것은 지금 가격 부담 하나뿐이다.
    금액은 숫자로 뽑히고("125만원이 부담"), 부담 표현도 좁은 목록으로 잡힌다.
    화제를 짐작하는 것이 아니라 고객이 **말한 대상**을 찾는 일이라 성격이 다르다.
    fit·timing 은 그렇게 뽑을 것이 없어서 자동으로 고르지 않는다.

    못 고르면 기본 응대(BASE_STANCE)로 둔다. 그래도 대화는 정상이다 —
    답을 만드는 장치(제품 상세·노트북 수납표·매장 안내·재고 표·보유 제품 브릿지)가
    전부 고객 발화를 따로 보고 붙기 때문이다.

    **`budget_max` 로는 켜지 않고 `concerns` 로만 켠다.**
    종전 게이트는 둘 다 허용했는데, 그건 AI 1 이 price 라고 말해준 뒤
    "돈 이야기가 오갔는가"를 확인하는 용도라 넓어도 됐다.
    지금은 이것이 전략을 **고르는** 조건이므로 같으면 안 된다.
      · concerns    "125만원은 부담스러워요"  → 부담을 말했다
      · budget_max  "예산이 120만원인데요"     → 예산을 밝혔을 뿐이다
    후자에 price 전략을 붙이면 첫 줄이 "적은 금액은 아니지요" 가 되는데,
    고객이 하지 않은 말을 확인해주는 형태다. 위에서 막으려던 바로 그것이다.

    예산만 밝힌 고객도 예산 분류표(build_budget_note)는 그대로 받는다.
    그건 전략과 별개로 붙으므로, 제품을 고르는 데 필요한 것은 빠지지 않는다.
    """
    if from_ai1:
        hesitation_type = None
    if hesitation_type is None and state["concerns"]:
        hesitation_type = "price"
    return hesitation_type


def build_extras(
    state,
    hesitation_type,
    constraint_is_old=True,
    strategy_repeated=True,
    customer=None,
):
    """이번 턴에만 붙일 지시들. 대화 기록에는 남기지 않는다.

    맨 뒤에 붙이는 이유: 모델은 가까이 있는 지시를 더 잘 따른다.

    조건 두 개를 따로 받는다. 원래 `has_history` 하나로 둘 다 썼는데,
    이름이 미끄러지면서 서로 다른 질문에 같은 답을 주고 있었다.

      constraint_is_old   예산·가격 조건을 **앞 턴에서** 말했는가
                          → "처음에 ~라고 하셨죠" 같은 회상 표현의 조건.
                            이번 턴에 처음 말한 것을 회상하면 한 적 없는 말이 된다.
      strategy_repeated   이 망설임 전략을 **이미 한 번 썼는가**
                          → 전략 본문을 다시 주입할지의 조건.
                            매 턴 다시 넣으면 세 턴 연속 같은 설명이 나온다.

    전에는 둘이 같이 움직여서 티가 안 났다. 고객이 "비싸다"고 말해야
    AI 1 이 price 를 보냈으니 예산 조건과 전략이 함께 생겼다.
    AI 1 이 클릭 행동으로 분류하면서 갈라졌다. 대화에서 가격 얘기를 한 마디도
    안 해도 PRICE_HESITANT 가 오므로, 예산 조건만 보면 억제가 영영 안 켜진다.
    """
    extras = []

    # 쌓인 조건 중 가장 빡빡한 상한을 적용한다.
    concerns = [c for c in state["concerns"] if c > 0]
    limit, exclusive = state.get("budget_max"), False
    if concerns:
        lowest = min(concerns)
        if limit is None or lowest <= limit:
            limit, exclusive = lowest, True

    if limit:
        extras.append(
            {
                "role": "system",
                "content": build_budget_note(limit, exclusive, customer),
            }
        )

    constraints = build_constraints_note(state, constraint_is_old)
    if constraints:
        extras.append({"role": "system", "content": constraints})

    # 이미 이 전략을 한 번 썼으면 본문을 다시 넣지 않는다.
    # 그대로 두면 같은 답이 반복되므로 반복 금지를 앞세운다.
    strategy = build_hesitation_strategy(hesitation_type, repeated=strategy_repeated)
    if strategy:
        extras.append({"role": "system", "content": strategy})

    return extras


# 모델이 빈 응답을 보냈을 때 재시도해도 안 되면 쓰는 마지막 문장.
# 사과하지 않고, 대화를 이어갈 수 있게 되묻는다.
FALLBACK_REPLY = "말씀을 놓쳤습니다. 한 번만 다시 여쭤도 될까요?"


def _create_with_retry(messages, attempts=4):
    """요청 한도(429)에 걸리면 잠시 기다렸다 다시 시도한다.

    지금 계정은 분당 30,000 토큰까지 쓸 수 있는데 시스템 프롬프트가 커서
    분당 두 번이면 한도에 닿는다. 데모 중에 대화를 빠르게 주고받으면 걸린다.
    그때 그냥 에러를 내면 시연이 멈추므로, 기다렸다 다시 보낸다.

    OpenAI 는 몇 초 뒤 재시도하라고 알려주므로 그 시간만큼 쉬면 대개 통과한다.
    """
    for attempt in range(attempts):
        try:
            return client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.7,
                response_format={"type": "json_object"},
            )
        except RateLimitError:
            if attempt == attempts - 1:
                raise
            # 5초, 12초, 25초 — 뒤로 갈수록 길게 기다린다.
            wait = 5 + attempt * 7 + attempt * attempt * 3
            print(
                f"[요청 한도] {wait}초 기다렸다 다시 시도합니다"
                f" ({attempt + 1}/{attempts - 1})",
                file=sys.stderr,
            )
            time.sleep(wait)


def _call(messages, allow_retry=True):
    """OpenAI 를 호출하고 {reply, suggested_action} 로 돌려준다.

    모델이 가끔 빈 JSON({})을 돌려준다. 그대로 두면 화면에 '{}' 가 찍히고
    대화가 끊긴다. 그래서 한 번 다시 시도하고, 그래도 비면 되묻는 문장을 보낸다.
    """
    response = _create_with_retry(messages)
    raw = (response.choices[0].message.content or "").strip()

    reply, action = "", "none"

    # JSON 이 깨져도 서비스가 죽지 않게 한다.
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            reply = str(data.get("reply", "")).strip()
            action = str(data.get("suggested_action", "none")).strip()
    except (json.JSONDecodeError, AttributeError, TypeError):
        # JSON 이 아니면 본문을 그대로 답변으로 본다.
        reply = raw

    if action not in VALID_ACTIONS:
        action = "none"

    # 빈 응답이거나 껍데기만 온 경우.
    if not reply or reply in ("{}", "{ }", "[]"):
        if allow_retry:
            nudge = {
                "role": "system",
                "content": (
                    "직전 응답이 비어 있었습니다. "
                    "reply 필드에 고객에게 보낼 문장을 반드시 담아 다시 답하세요. "
                    "빈 객체를 보내지 마세요."
                ),
            }
            return _call(messages + [nudge], allow_retry=False)
        return {"reply": FALLBACK_REPLY, "suggested_action": "none"}

    return {"reply": reply, "suggested_action": action}


def generate_reply(
    message,
    customer_id=None,
    conversation_history=None,
    hesitation_type=None,
    owned_products=None,
    variant="default",
    pick_hint="",
):
    """고객 발화 하나에 대한 답변을 만든다. (팀 합의 스펙의 입력을 그대로 받는다)

    variant 는 응대 전략 버전이다. (개발 단계 6, Persona Bot Lab 실험용)

    pick_hint (2026-08-18, 통합 경로용): 제품 매칭 텍스트에만 덧붙는 힌트.
    통합 레이어가 "고객이 지금 보고 있는 제품"을 보내주는데, 고객이 발화에서
    이름을 안 불렀어도 그 제품 상세가 잡히게 한다. message 나 대화 기록에
    덧붙이면 고객이 안 한 말이 생기므로(대화 오염) 매칭 입력에만 잇는다.
    기본값 "" — /chat 경로는 아무것도 달라지지 않는다.
    """

    # 들어온 값을 여기서 한 번 정리한다.
    # 아래 블록들이 전부 이 값들을 훑으므로, 입구에서 맞춰두면
    # 뒤쪽은 형식을 가정해도 안전하다.
    message = _clean_text(message)
    customer_id = _clean_text(customer_id) or None
    variant = _clean_variant(variant)
    conversation_history = _clean_history(conversation_history)
    is_control = variant == "control"

    # AI 1 라벨(PRICE_HESITANT 등)로 와도 받는다. 우리 값이면 그대로 통과한다.
    # 여기 한 곳에서만 옮기면 아래 블록들은 우리 이름만 보면 된다.
    #
    # 옮기기 전에 "AI 1 이 보낸 값인가"를 기억해둔다.
    # AI 1 분류는 세션 단위라 대화 중에 값이 바뀌지 않는다.
    # (지표가 nunique/max 라 클릭이 쌓여도 줄지 않는다 — 전이가 한 방향이다)
    # 그래서 앞 턴이 있으면 같은 전략을 이미 한 번 쓴 것으로 본다.
    from_ai1 = (
        isinstance(hesitation_type, str)
        and hesitation_type.strip().upper() in LABEL_MAP
    )
    hesitation_type = normalize_hesitation(hesitation_type)

    # 고객이 제품 상태나 케어를 언급했을 때만 컨디션 상세를 보여준다.
    # 프롬프트에 있으면 모델은 결국 인용하므로, 자리가 아니면 아예 가린다.
    talked = " ".join(
        [m.get("content", "") for m in conversation_history if m.get("role") == "user"]
        + [message]
    )
    allow_condition = any(hint in talked for hint in CONDITION_TALK_HINTS)

    system = build_system_prompt(variant)
    customer = build_customer(customer_id, owned_products)
    if customer:
        # 보유 제품의 상세(구매 시점·케어 이력)를 보여줄 자리인지 판단한다.
        # 케어 화제이거나 고객이 그 제품을 직접 말했을 때만 보여준다.
        # 그냥 두었더니 재고를 묻는 고객에게 케어를 얹었다.
        lowered = talked.lower()
        allow_owned = any(hint in lowered for hint in OWNED_TOPIC_HINTS) or any(
            (p.get("name") or " ").split()[0] in talked
            for p in customer.get("owned_products") or []
        )
        system += build_customer_block(
            customer,
            rules=not is_control,
            allow_condition=allow_condition or is_control,
            allow_owned=allow_owned or is_control,
            # 이번 발화가 어떤 서비스를 묻는지에 따라 매장 정보를 추린다.
            message=message,
            # 지역은 대화 전체에서 본다. 두 턴 전에 "부산이요" 라고 하셨으면
            # 그 뒤로도 부산으로 안내해야 한다.
            talked=talked,
        )
    system += OUTPUT_FORMAT

    # 지금까지 고객이 한 말 + 이번 발화에서 조건을 다시 계산한다.
    past_user_texts = [
        m["content"] for m in conversation_history if m.get("role") == "user"
    ]
    state = derive_constraints(past_user_texts + [message])

    hesitation_type = pick_strategy(hesitation_type, from_ai1, state)

    # "처음에 ~라고 하셨죠" 는 그 조건을 **앞 턴에서** 말했을 때만 성립한다.
    # 대화에 앞선 턴이 있는지만 봤더니, 이번 턴에 처음 가격 부담을 말한 고객에게
    # "처음에 가격이 마음에 걸린다고 하셨죠"라고 답했다. 한 적 없는 말이다.
    past_state = derive_constraints(past_user_texts)
    constraint_is_old = bool(past_state["concerns"]) or bool(past_state["budget_max"])

    # 전략을 이미 썼는지는 원래 다른 질문이지만, 여기서는 같은 답이 된다.
    #
    # 한때 `constraint_is_old or (from_ai1 and past_user_texts)` 로 넓혔다가 되돌렸다.
    # 위 게이트 때문에 price 전략은 **고객이 가격을 말했을 때만** 걸린다.
    # 그러면 "앞 턴에 전략이 걸렸는가"와 "앞 턴에 가격 얘기가 있었는가"가 같은 말이다.
    #
    # 넓혀뒀더니 사고가 났다. 1턴에 가격 얘기가 없어 전략이 안 걸렸는데,
    # 2턴에 고객이 "125만원은 부담되네요" 라고 하자 "이미 대응했으니 반복 말라"가 들어가
    # 헤리티지 이야기가 통째로 빠지고 곧장 가격표로 넘어갔다.
    # 한 번도 하지 않은 것을 이미 했다고 가정한 것이다.
    #
    # 2026-08-18: AI 1 라벨이 전략을 고르지 않게 되면서 이 등식이 오히려 더 튼튼해졌다.
    # 자동으로 걸리는 전략은 price 하나뿐이고, 그 조건이 곧 가격 조건이다.
    strategy_repeated = constraint_is_old

    # 대조군에는 우리가 만든 보조 장치(예산 분류, 누적 조건, 망설임 전략)를 붙이지 않는다.
    # 그것들도 우리 설계의 일부이므로, 대조군에 주면 비교가 흐려진다.
    # 붙이는 순서가 중요하다. 모델은 가까이 있는 지시를 더 잘 따르므로,
    # 판단이 흔들리기 쉬운 것(예산 분류, 누적 조건, 망설임 전략)을 맨 뒤에 둔다.
    # 앞에 두었더니 "140만원 이하에 145만원 제품이 있습니다" 같은 모순이 나왔다.
    extras = []
    check_source = False
    continuity = ""

    if not is_control:
        # 우리가 확정해서 답할 수 없는 주제면 응대 틀을 넘긴다.
        unanswerable = build_unanswerable_note(message)
        if unanswerable:
            extras.append({"role": "system", "content": unanswerable})

        # 제품 상세는 이번 대화에 등장한 것만 넣는다. (전부 넣으면 4,400 토큰)
        _text_parts = [m.get("content", "") for m in conversation_history] + [message]
        _hint = _clean_text(pick_hint)
        if _hint:
            _text_parts.append(_hint)
        conversation_text = " ".join(_text_parts)
        # 추천을 묻는 턴에서는 보유 제품 상세를 뺀다.
        # 보여주면서 "권하지 마라"고 하면 모델이 그 지시를 해설한다.
        # 판단은 이번 발화만 본다 — hides_owned_detail() 의 주석 참고.
        detail = build_product_detail(
            pick_products(
                conversation_text,
                customer,
                include_owned=not hides_owned_detail(message),
            ),
            customer,
        )
        if detail:
            extras.append({"role": "system", "content": detail})

        # 노트북 수납 표는 **고객이** 노트북 이야기를 꺼냈을 때만 붙인다.
        # 대화 전체로 판단했더니, 앞 턴에 에이전트가 스스로 언급한 것 때문에
        # 표가 계속 따라붙어 "무게가 걱정된다"는 고객에게 인치를 되물었다.
        if needs_laptop_table(talked):
            extras.append({"role": "system", "content": build_laptop_table()})

        # 망설임 유형에 필요한 헤리티지 섹션이 기본에 없으면 추가한다.
        extra_heritage = build_extra_heritage(hesitation_type)
        if extra_heritage:
            extras.append({"role": "system", "content": extra_heritage})

        if customer:
            # 매장·재고 이야기가 나온 턴에만 확장 규칙을 붙인다. (약 3,000자)
            if needs_store_extra(message):
                extras.append(
                    {"role": "system", "content": build_store_extra(customer, talked)}
                )
                # 대화에 등장한 제품의 매장별 재고. 시연용 가정값이다.
                # 모델이 지어내게 두면 매번 답이 달라져서 리허설이 무의미해진다.
                stock_table = build_stock_table(
                    pick_products(conversation_text, customer), customer, talked
                )
                if stock_table:
                    extras.append({"role": "system", "content": stock_table})

                # 어느 도시의 재고를 확인할지는 코드가 정한다.
                # 프롬프트로 두었더니 현재지와 귀국지 사이에서 계속 흔들렸다.
                decision = build_stock_decision(customer, message, conversation_text)
                if decision:
                    extras.append({"role": "system", "content": decision})

            # 고객이 직접 말한 지역이 있으면 그 지역 매장을 열어준다.
            # 매장을 현재 위치에만 잠가두면, "다음 달 서울 가는데 거기서 받을까요"에
            # 답할 수가 없다.
            mentioned = build_mentioned_region_note(message, customer)
            if mentioned:
                extras.append({"role": "system", "content": mentioned})

        # 우리가 매장을 모르는 지역을 고객이 말했을 때의 응대 틀.
        # 고객이 없어도(customer=None) 동작해야 하므로 바깥에 둔다.
        place = build_place_note(message, customer or {})
        if place:
            extras.append({"role": "system", "content": place})

        # 맨 뒤 — 예산 분류, 누적 조건, 망설임 전략
        extras += build_extras(
            state,
            hesitation_type,
            constraint_is_old=constraint_is_old,
            strategy_repeated=strategy_repeated,
            customer=customer,
        )

        # 보유 제품과 이어지는 질문이면, 출처가 붙은 표현을 미리 만들어 넘긴다.
        # 고객이 말한 것만 넘긴다(talked). 에이전트가 앞 턴에 꺼낸 제품을
        # "이미 나온 것"으로 치면 출처 표현이 만들어지지 않는다.
        #
        # 위치가 뒤인 이유: 오늘 블록을 여럿 추가하자 브릿지가 밀려나면서
        # 모델이 출처 없이 "현재 사용 중인 Liz" 라고 꺼내기 시작했다.
        # 출처는 이 프로젝트에서 가장 중요한 규칙이라 뒤쪽에 둔다.
        if customer:
            # 고객 발화 + 우리가 이미 출처를 밝히며 소개한 제품까지 본다.
            #
            # 고객 발화만 보면, 오프닝에서 "2024년 2월에 Pina 클리닝을 해드렸습니다"
            # 라고 소개해놓고 몇 턴 뒤 "구매 기록을 보니 Pina가 있으시네요" 라고
            # 처음 보는 것처럼 다시 꺼낸다.
            # 반대로 에이전트 발화를 전부 보면, 출처 없이 흘린 언급까지 '이미 나온 것'이
            # 되어 출처를 밝힐 기회를 잃는다. 그래서 출처가 붙은 언급만 인정한다.
            introduced = " ".join(
                m.get("content", "")
                for m in conversation_history
                if m.get("role") == "assistant"
                and any(
                    mark in m.get("content", "")
                    for mark in (
                        "구매 기록", "케어 접수 기록",
                        "해드렸", "봐드렸", "살펴드렸", "드렸었",
                    )
                )
            )
            # 이미 한 번 출처를 밝히며 보유 제품을 꺼냈다면 다시 꺼내지 않는다.
            # 세션당 한 번이라는 규칙을 코드로 강제한다.
            #
            # 다른 제품을 대신 내밀었더니 모델이 그것을 대화 주제로 바꿔버렸다.
            # (Pina 케어 제안에 고객이 "네"라고 했는데 Aren 안내가 나갔다)
            # 대화가 이미 보유 제품 케어로 진행 중이면 다리를 놓을 이유가 없다.
            bridge = build_owned_bridge(customer, message, talked)
            # 이미 한 번 소개했으면 다시 소개하지 않는다.
            # 다만 '어느 제품인지 되묻기'는 소개가 아니라 확인이므로 살린다.
            # 억제가 되묻기까지 막았더니, "이건 수선이 어렵다던데요" 에
            # 제품을 확인하지 않고 엉뚱한 안내로 넘어갔다.
            if introduced and "어느 제품인지 아직 모릅니다" not in bridge:
                bridge = ""
            if bridge:
                extras.append({"role": "system", "content": bridge})
                # 우리가 먼저 꺼내는 턴이다. 이 턴에만 출처를 검사한다.
                check_source = "어느 제품인지 아직 모릅니다" not in bridge

            # "7년 썼으면" 처럼 기간을 말하면 어느 제품인지 코드가 지목한다.
            # 경과 기간 표를 줘도 모델이 다른 제품을 골랐다.
            duration = match_by_duration(customer, message)
            if duration:
                extras.append({"role": "system", "content": duration})

            # 고객이 "네"처럼 짧게 수락했으면 그 대상을 코드가 고정한다.
            # 오프닝에서 Pina 케어를 제안했는데 "네, 봐주세요"에 Aren 안내가 나갔다.
            continuity = build_continuity_note(customer, message, conversation_history)
            if continuity:
                extras.append({"role": "system", "content": continuity})

        # 앞 턴 답을 되풀이하지 않게 직전 발화를 그대로 보여준다.
        #
        # "반복하지 마라"는 BASE_STANCE 와 FINAL_CHECK 에 이미 있는데도 안 지켜졌다.
        # 무엇이 반복인지는 직전 답변을 봐야 아는데 그것이 대화 기록 위쪽에 묻혀 있어서다.
        #
        # 세 자리에는 붙이지 않는다. 겹치는 것이 정상인 자리다.
        #   · 짧은 수락 — 앞의 제안을 이어받아야 한다
        #   · 출처 추궁 — 앞에서 꺼낸 제품을 다시 언급해야 답이 성립한다
        #   · 짧은 답변 — 우리가 되물은 것에 답한 턴 (함수 안에서 길이로 거른다)
        # 이 프로젝트에서 억제 규칙은 늘 필요한 것까지 억제했다.
        # 지난 턴들의 고객 발화만 넘긴다. 이번 발화(추궁 문장)에는 제품 이름이
        # 들어 있어서, 포함하면 "고객이 말한 것"으로 잘못 세어진다.
        past_user_text = " ".join(
            m.get("content", "")
            for m in conversation_history
            if m.get("role") == "user"
        )
        challenge = build_source_challenge_note(message, customer, past_user_text)
        if not continuity and not challenge:
            no_repeat = build_no_repeat_note(conversation_history, message)
            if no_repeat:
                extras.append({"role": "system", "content": no_repeat})

        # 진짜 맨 뒤 — 응답 언어.
        # 한국어면 빈 문자열이라 아무것도 붙지 않는다.
        # 앞쪽 블록들이 한국어 예시 문장을 잔뜩 담고 있어서, 언어 지시가 앞에 있으면
        # 모델이 그 예시를 따라 한국어로 돌아간다. 그래서 가장 뒤에 둔다.
        language = build_language_note(message, customer or {})
        if language:
            extras.append({"role": "system", "content": language})

        # 진짜 마지막 — 자주 놓치는 셋
        extras.append({"role": "system", "content": FINAL_CHECK})

        # 뜻을 알 수 없는 입력이면 화제를 만들지 말고 되묻게 한다.
        # 붙잡을 것이 없으면 모델은 프롬프트의 강한 지시를 화제로 착각한다.
        unclear = build_unclear_note(message)
        if unclear:
            extras.append({"role": "system", "content": unclear})

        # 그보다 더 마지막 — 출처를 추궁당한 순간.
        # 이 프로젝트에서 가장 중요한 장면이고, 앞의 어떤 지시보다 우선한다.
        # 출력 점검을 맨 뒤에 놓자 "접수를 도와드릴까요?" 로 끝나면서
        # 통제권을 드리는 문장이 사라졌다.
        # (challenge 는 위 반복 금지 블록에서 이미 계산해두었다)
        if challenge:
            extras.append({"role": "system", "content": challenge})

    messages = (
        [{"role": "system", "content": system}]
        + list(conversation_history)
        + [{"role": "user", "content": message}]
        + extras
    )

    result = _call(messages)

    # _call 은 reply 를 항상 문자열로 돌려주지만, 아래 검사들이 그 계약에
    # 기대고 있으므로 여기서 한 번 더 확인한다.
    # 계약이 바뀌면 검사 쪽이 조용히 터진다.
    if not isinstance(result.get("reply"), str):
        result["reply"] = FALLBACK_REPLY
    if result.get("suggested_action") not in VALID_ACTIONS:
        result["suggested_action"] = "none"

    # 출처 없이 보유 제품을 꺼냈으면 한 번 다시 요청한다.
    #
    # 이 프로젝트에서 가장 중요한 규칙인데 프롬프트로는 세 번 실패했다.
    # 출처가 붙은 표현을 만들어 넘겨도 "현재 사용 중인 Liz", "2023년에 구매하신 Liz"
    # 처럼 줄여 쓴다. 표현을 강제하는 것은 프롬프트가 잘 못하는 일이다.
    # 그래서 결과를 코드가 검사하고, 어겼으면 그 사실을 알려주고 다시 받는다.
    # 검사는 브릿지가 붙은 턴에만 한다.
    #
    # 한 번 `or customer` 로 넓혀봤다가 되돌렸다.
    # 거의 모든 턴에서 재요청이 걸리고, 재요청 문구가 "이 표현으로 바꿔서
    # 답변 전체를 다시 쓰라" 이다 보니 모델이 그 문장 중심으로 답을 다시 만들어
    # 원래 질문을 잃었다. "얼마나 걸려요?" 에 기간 대신 보유 제품 안내가 나왔고,
    # 두 턴 연속 똑같은 답변이 찍혔다.
    #
    # 출처 없는 언급이 가끔 새는 것보다 대화가 어긋나는 쪽이 훨씬 나쁘다.
    if check_source:
        missing = _unsourced_owned(result.get("reply", ""), customer, talked)
        if missing:
            result = _call(messages + [{"role": "system", "content": missing}])

    # 이미 가진 제품을 대안으로 권했으면 한 번 다시 요청한다.
    #
    # **예산·가격 이야기가 오간 턴에만 검사한다.**
    # 이 검사는 "예산에 맞는 대안으로 Liz 쇼퍼가 있습니다" 를 막으려고 만든 것이다.
    # 조건 없이 걸었더니 케어 대화에서도 발동해서, "네, 한번 봐주세요" 에
    # "Pina 는 이미 사용 중이라 다른 대안은 없네요" 라고 답했다.
    # 케어 요청을 구매 문의로 바꿔 읽은 것이다.
    #
    # 재요청은 답변 전체를 다시 만들게 하므로 대화 틀까지 흔든다.
    # 범위를 좁히지 않으면 고치는 것보다 깨뜨리는 것이 많다.
    price_context = bool(state["budget_max"]) or bool(state["concerns"])
    if customer and not is_control and price_context:
        again = _recommended_owned(result.get("reply", ""), customer, talked)
        if again:
            result = _call(messages + [{"role": "system", "content": again}])

    # 아직 사지 않은 제품에 delivery 가 붙었으면 정정한다.
    if customer and not is_control:
        result = fix_delivery_action(result, customer)

    # 지역을 조건절에 넣은 표현을 선택 조건으로 바꾼다.
    # ("부산에 계시다면" → "부산이 편하시다면")
    #
    # 프롬프트로 두 번 시도했는데, 그 규칙이 답변에서 14,000자 떨어져 있어 묻혔다.
    # 답변 가까이로 옮기면 지켜지지만 맨 뒤 자리는 하나뿐이라 다른 규칙이 밀린다.
    # 문자열 치환으로 끝나는 일이므로 프롬프트를 쓰지 않고 코드가 한다.
    # 모델을 다시 부르지 않아 대화가 어긋날 위험도 없다.
    if customer and not is_control:
        result["reply"] = fix_region_condition(result.get("reply", ""), customer)

    return result


def generate_outreach(
    customer_id, owned_products=None, variant="default", hesitation_type=None
):
    """에이전트가 먼저 건네는 첫 메시지를 만든다. 고객 발화가 없어도 동작한다.

    hesitation_type 은 AI 1 이 클릭 행동으로 낸 분류다. **여기가 그 신호의 자리다.**
    대화 중(generate_reply)에는 쓰지 않는다. 고객이 입을 열면 그때부터는
    말한 것이 근거여야 하고, 행동으로 속마음을 단정하면 감시가 되기 때문이다.
    아직 아무 말도 하지 않은 고객에게는 단정할 것도 없다.
    우리는 무슨 이야기로 문을 열지 고르는 것뿐이다.
    """

    # generate_reply 와 같은 자리에서 같은 방식으로 정리한다.
    customer_id = _clean_text(customer_id) or None
    variant = _clean_variant(variant)

    customer = build_customer(customer_id, owned_products)
    if not customer:
        raise ValueError("먼저 말을 걸려면 customer_id 가 필요합니다.")

    # 먼저 말을 거는 데는 계기가 있어야 한다.
    #
    # 착장 기록이나 케어 시점 같은 사건이 없으면 건넬 말이 없다.
    # 그래도 억지로 열게 하면 모델이 카탈로그에서 제품을 하나 골라
    # 고객이 본 적도 없는 것을 본 것처럼 말한다.
    #
    # 실서비스에서는 사건이 발생했을 때만 시스템이 이 함수를 부르므로
    # 이 경우는 호출하는 쪽의 실수다. 지어내는 대신 분명히 알린다.
    if pick_opening_material(customer) is None:
        raise ValueError(
            f"{customer_id} 에게 먼저 말을 걸 계기가 없습니다. "
            "착장·조회·구매 기록이나 보유 제품 중 하나는 있어야 합니다."
        )

    if variant == "control":
        # 대조군에는 먼저 말 거는 방법에 대한 설계를 주지 않는다.
        # 일반적인 챗봇이 알아서 보내는 첫 메시지가 어떤지 보기 위함이다.
        system = (
            build_system_prompt("control")
            + build_customer_block(customer, rules=False)
            + "\n\n고객에게 먼저 보낼 메시지를 작성하세요.\n"
            + OUTPUT_FORMAT
        )
    else:
        # 이 고객과 관련된 제품(방금 본 것, 보유 중인 것)만 상세히 넣는다.
        detail = build_product_detail(pick_products("", customer), customer)
        system = (
            build_system_prompt(variant)
            # 오프닝에서는 컨디션을 절대 꺼내지 않는다.
            # 고객이 아직 아무 말도 하지 않았으므로 상태를 말할 자격이 없다.
            # 규칙으로만 막았더니 4o 가 "가죽 핸들의 색이 옅어진 부분" 을 인용했다.
            # 프롬프트에 있으면 결국 인용하므로 여기서는 아예 가린다.
            + build_customer_block(customer, allow_condition=False)
            + detail
            # AI 1 행동 분류가 쓰이는 유일한 자리.
            # 지침 안쪽(재료 바로 아래)으로 들어간다. 뒤에 따로 붙였더니
            # "위 재료만 씁니다"로 끝나는 4,000자 지침에 묻혀 효과가 없었다.
            + build_outreach_instruction(customer, hesitation_type)
            + OUTPUT_FORMAT
            + FINAL_CHECK
            # 고객 발화가 없으므로 프로필의 주 언어를 따른다.
            # 영어를 더 편하게 쓰는 고객에게 한국어로 먼저 말을 걸고 있었다.
            + build_language_note("", customer)
        )

    return _call([{"role": "system", "content": system}])
