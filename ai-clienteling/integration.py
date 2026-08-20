"""[미사용 — 2026-08-18 폐기] 통합 모드 — /clienteling/reply 전용 응답 생성이었다.

폐기 사유: 이 모듈은 팀 계약의 전제("시스템이 지금 보는 제품 하나를 실어준다")를
채택해 어드바이저가 한 제품만 아는 구조였다. 그 결과 다른 제품을 물으면
"정보가 없습니다", 재고·매장·픽업은 전부 확인 인수로 퇴화 — 우리 서비스의 전제
("어드바이저는 전 제품을 안다")를 깼다. 사용자 손 테스트가 이를 드러냈고,
/clienteling/reply 는 기존 MCM 엔진 + knowledge.data_overlay(18종 카탈로그) 로
재설계됐다 (api.py 참고).

파일을 남겨두는 이유: 팀이 최종적으로 "요청 데이터만 아는 브랜드 중립 모드"로
결정하면 되살릴 폴백이다. 여기서 잡았던 결함 수정(날짜 문구 코드화, 무근거 입력,
추궁 확장, 기간·세일 지어내기 방지)의 기록이기도 하다.

―――――― 이하 폐기 전 원문 ――――――
"""
_ORIGINAL_DOC = """통합 모드 (2026-08-18) — /clienteling/reply 전용 응답 생성.

팀 통합 레이어는 **브랜드 중립 메종** 세계관이다 (fixtures 정책: "실존 브랜드명을
쓰지 않는다"). 그래서 이 경로에서는 MCM 지식 베이스(매장·헤리티지·재고 표·
카탈로그·예산 분류)를 쓰지 않는다. 제품 지식은 **매 요청의 target_product 가 전부**다.
카탈로그 파일을 복사해오지 않는 이유: 사본은 반드시 어긋난다. 요청에 실려오는
데이터를 그 턴의 지식으로 쓰면 동기화 문제가 원천적으로 없다.

MCM 데모 경로(engine.generate_reply / generate_outreach)는 이 파일에서 호출만 하고
절대 수정하지 않는다 — 동결 유지가 이 분리의 목적이다.

엔진에서 재사용하는 것 (브랜드 중립인 재료만):
  - engine._call            JSON 강제·빈 응답 재시도·액션 검증
  - engine.OUTPUT_FORMAT    출력 형식 지시 (액션 5종 정의)
  - engine.FINAL_CHECK      맨 뒤 점검 (빈 마무리·반복·문장 수)
  - knowledge 의 케어/상태 화제 단어들 (컨디션 노트 가림 판정)
"""

import re

import engine
from prompts.knowledge import (
    CONDITION_TALK_HINTS,
    OWNED_TOPIC_HINTS,
    build_source_challenge_note,
    build_unclear_note,
)

# 브랜드 중립 인격. system_prompt.SYSTEM_PROMPT_V1 에서 MCM 고유 요소
# (뮌헨 1976, 비세토스, 매장)를 뺀 증류판이다. 원칙 층은 같다.
INTEGRATION_PROMPT = """당신은 럭셔리 메종의 퍼스널 어드바이저입니다.
부티크에서 오래 일해온 사람의 태도로 고객을 대합니다.

# 당신이 누구인가
당신은 판매원이 아니라, 고객의 물건을 아는 사람입니다.
고객이 무엇을 살지보다, 고객이 이미 가지고 있는 것이 지금 어떤 상태인지를 먼저 생각합니다.
잘 만든 물건이 오래 쓰이는 것이 이 메종의 자부심입니다.

# 절대 규칙

## 1. 케어 우선
고객의 제품에 마모나 사용감이 보여도, 새 제품 구매를 먼저 권하지 않습니다.
케어와 수선을 먼저 제안합니다. 교체는 수선으로 해결이 불가능할 때, 또는
고객이 먼저 물어봤을 때만 언급합니다.

## 2. 럭셔리 톤
할인·쿠폰·한정 수량 같은 판매 압박 화법을 쓰지 않습니다. 재촉하지 않습니다.
고객이 사지 않기로 해도 그 선택을 존중합니다.

## 3. 진단서 화법 금지
제품 컨디션을 수치나 판정으로 말하지 않습니다. 점수·등급·임계치 같은 단어를
고객에게 쓰지 않습니다. 사진을 받지 않았으므로 "보이네요" 처럼 직접 본 듯한
표현도 쓰지 않습니다.

## 4. 지어내지 않기
아래 "제품 정보" 블록에 적힌 것이 이 제품에 대해 아는 **전부**입니다.
거기 없는 실측 치수·무게·재고 상세·매장 위치·배송 기간은 추측해서 말하지 않고,
"확인해서 알려드리겠다"고 말합니다. 모른다고 끝내지 않고 확인을 인수합니다.
수선·케어의 소요 기간과 비용도 우리가 모릅니다. "보통 1~2주" 처럼 통상 수치를
지어내지 않습니다 — 접수 후 확인해서 안내드리겠다고 말합니다.
세일·프로모션은 **있다고도 없다고도** 단정하지 않습니다. 우리 정보에 없을 뿐
세상에 없는 것이 아닙니다. 확인해서 안내드리겠다고 말합니다.
실존 브랜드명을 언급하지 않습니다.
재고를 잡아두거나 제품을 준비해두겠다고 약속하지 않습니다 — 그건 매장이 정하는
일입니다. 우리가 할 수 있는 것은 확인 요청을 넣어드리는 것까지입니다.

## 5. 보유 제품은 출처와 함께
고객의 보유 제품을 우리가 먼저 꺼낼 때는 "구매 기록"이라는 출처를 함께 말합니다.
"보유하고 계신", "현재 사용 중인" 은 출처가 아닙니다 — 어떻게 아는지가 빠져 있어
고객이 "그걸 어떻게 아세요?" 를 묻게 만듭니다. "구매 기록에 있는 X",
"구매 기록을 보니" 처럼 경로가 담긴 표현을 씁니다.
컨디션 이야기는 고객이 상태를 먼저 말했을 때만 합니다.

# 말하는 방식
한국어 존댓말. 담백하고 짧게. 3~5문장, 길어도 6문장. 이모지 금지.
질문은 한 번에 하나. 번호 목록 없이 이어지는 문장으로. 문단을 나누지 않습니다.
선택지를 나열하지 않고 가장 적합한 하나를 권합니다.
"어떠신가요?", "언제든 말씀해 주세요" 같은 빈 마무리를 붙이지 않습니다.
"""

# 카테고리 코드 → 고객에게 쓸 수 있는 말. 모르는 코드는 아예 말하지 않는다.
CATEGORY_KO = {"BAG": "백", "SHOES": "슈즈", "SLG": "지갑·소품", "RTW": "의류"}


def _product_block(product):
    """target_product dict → 프롬프트 텍스트. 있는 필드만 적는다.

    없는 필드를 빈칸으로 보여주면 모델이 그 자리를 채운다(지어낸다).
    """
    if not isinstance(product, dict):
        return ""
    name = str(product.get("name") or "").strip()
    if not name:
        return ""
    lines = [f"제품명: {name}"]
    category = CATEGORY_KO.get(str(product.get("category") or ""))
    if category:
        lines.append(f"종류: {category}")
    for key, label in (
        ("collection", "컬렉션"),
        ("material", "소재"),
        ("color", "컬러"),
        ("size_label", "사이즈"),
        ("size_system", "사이즈 체계"),
        # 저쪽 fixture 의 사이즈 호환 체계. 같은 코드끼리 치수가 호환된다 —
        # 저쪽 사이즈 상담의 근거 필드인데 처음에 빠뜨렸었다.
        ("last_code", "사이즈 호환 코드 (같은 코드끼리 치수 호환)"),
        # MCM 제품처럼 실측 데이터가 있는 경우. 보내는 쪽이 문장으로 만들어
        # 넣는 필드라, 여기 없는 제품은 이 줄이 안 생긴다 (없으면 인용할 수 없다).
        ("dimensions_note", "실측 치수"),
        ("laptop_note", "노트북 수납"),
        ("care_notes", "케어 안내"),
    ):
        value = str(product.get(key) or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    price = product.get("price_krw")
    if isinstance(price, (int, float)) and price > 0:
        lines.append(f"가격: {int(price):,}원")
    # "보유 사이즈" 라고 썼더니 모델이 **고객이** 보유한 것으로 잘못 읽었다
    # ("두 사이즈 모두 보유하고 계시기 때문에"). 주어를 라벨에 박는다.
    sizes = product.get("available_sizes")
    if isinstance(sizes, list) and sizes:
        lines.append(f"부티크에서 구매 가능한 사이즈: {', '.join(str(s) for s in sizes)}")
    else:
        stock = product.get("stock_by_size")
        if isinstance(stock, dict):
            in_stock = [str(k) for k, v in stock.items() if isinstance(v, (int, float)) and v > 0]
            if in_stock:
                lines.append(f"부티크에서 구매 가능한 사이즈: {', '.join(in_stock)}")
    return (
        "# 상담 대상 제품 정보 (이 제품에 대해 아는 전부)\n"
        + "\n".join(lines)
        + "\n여기 없는 정보는 지어내지 말고 확인을 인수합니다."
        + f"\n**이 정보는 위 제품({name})에만 해당합니다.** 고객이 다른 제품을"
        + " 말씀하시면 이 사이즈·수치를 그 제품에 옮겨 쓰지 않습니다."
        + " 그 제품의 정보는 우리에게 없으므로 확인을 인수합니다."
    )


def _unclear(message):
    """뜻을 읽어낼 수 없는 입력인가. 한글이 없고, 말로 보이는 영단어도 없을 때."""
    text = (message or "").strip()
    if not text:
        return False
    if any("가" <= ch <= "힣" for ch in text):
        return False
    words = re.findall(r"[A-Za-z]{2,}", text)
    return not (len(words) >= 2 or any(len(w) >= 4 for w in words))


def _unknown_product_tokens(message, target_product, owned_assets):
    """고객 발화 속, 우리가 모르는 제품 이름으로 보이는 토큰.

    "Aren 토트 백 사려고 하는데" — 대상 제품(Derby) 데이터가 실려 있으면 모델은
    둘이 다른 제품인 것을 모르고 Derby 의 사이즈를 옮겨 답했다 (mini 3/3, 4o 1/3.
    "Aurelia 토트 백" 같은 혼종까지 나왔다). 규칙 문장으로는 안 잡혀서 코드가 판정한다.

    한국어 문장 속 라틴 대문자 토큰은 사실상 제품·라인 이름이다. 대상·보유 제품
    이름에 없는 것이 나오면 "모르는 제품을 말씀하셨다"로 본다.
    (영어 발화가 들어오면 오탐할 수 있다 — 통합 모드는 현재 한국어 전제)
    """
    known = set()
    if isinstance(target_product, dict):
        known |= set(str(target_product.get("name") or "").split())
    for a in owned_assets or []:
        if isinstance(a, dict):
            known |= set(str(a.get("product_name") or "").split())
    # 악센트 문자를 빼먹으면 "Solène" 이 "Sol" 로 잘려 모르는 제품으로 오판된다.
    # 실제로 저쪽 fixture 12종 중 4종(Solène·Marée·Lisière×2)이 이 오판으로
    # "정보가 없습니다" 를 받았다. 라틴 확장 문자까지 한 토큰으로 읽는다.
    tokens = re.findall(r"[A-ZÀ-ÖØ-Þ][A-Za-zÀ-ÖØ-öø-ÿ0-9®-]{2,}", message or "")
    return [t for t in tokens if t not in known]


def _care_context(message):
    """이번 발화가 상태·케어 이야기인가. 컨디션 노트를 보여줄지 이걸로 정한다."""
    text = (message or "").lower()
    return any(w in text for w in CONDITION_TALK_HINTS) or any(
        w in text for w in OWNED_TOPIC_HINTS
    )


def _owned_block(owned_assets, message):
    """보유 자산 → 프롬프트 텍스트.

    condition_score·severity·next_service_months 는 넣지 않는다 (진단서 화법의 원인).
    소견 문장(note)도 고객이 상태·케어를 먼저 말한 턴에만 보여준다.
    없으면 인용할 수 없다 — MCM 경로와 같은 수법이다.
    """
    lines = []
    show_notes = _care_context(message)
    for asset in owned_assets or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("product_name") or "").strip()
        if not name:
            continue
        # "2023-04" 를 모델이 "작년 4월" 로 옮긴 사고가 있었다 (지금은 2026년).
        # 날짜 계산은 모델에게 맡기지 않는다 — 말할 문구를 코드가 만들어 준다.
        raw = str(asset.get("purchased_at") or "")
        line = f"- 구매_기록에_있는_제품: {name}"
        if len(raw) >= 7 and raw[:4].isdigit() and raw[5:7].isdigit():
            line += f" (구매 시점: {int(raw[:4])}년 {int(raw[5:7])}월)"
        if show_notes:
            notes = "; ".join(
                str(f.get("note") or "").strip()
                for f in asset.get("findings") or []
                if isinstance(f, dict) and f.get("note")
            )
            if notes:
                line += f" / 접수 기록 소견: {notes}"
        lines.append(line)
    if not lines:
        return ""
    return (
        "# 고객의 구매 기록\n"
        + "\n".join(lines)
        + "\n여기 적힌 것(제품명·구매 시점)이 구매 기록에서 아는 **전부**입니다."
        + "\n보유 제품의 사이즈·색상·상태를 지어내지 않습니다. 기록에 없습니다."
        + "\n이 제품을 우리가 먼저 꺼낼 때는 구매 기록이 출처임을 밝힙니다."
        + "\n'보유하고 계신' 이라고만 말하지 않습니다 — '구매 기록에 있는' 으로 씁니다."
        + "\n보유 제품은 지금 화제와 **종류가 이어질 때만** 근거로 씁니다."
        + " 슈즈 기록으로 백의 사이즈를 조언하는 식으로, 종류가 다른 제품에"
        + " 끌어다 쓰지 않습니다. 이어지지 않으면 아예 꺼내지 않습니다."
        + "\n구매 시점은 적힌 표기 그대로 씁니다. 오늘 날짜를 모르므로"
        + " '작년'·'재작년' 같은 상대 표현으로 바꾸면 틀립니다."
    )


# 망설임 라벨별 짧은 지침. 통합 레이어가 세션 분류를 함께 보내는 계약이라
# MCM /chat 과 달리 여기서는 쓴다 — 저쪽 데모의 축(사이즈 상담)이 이 값에 걸려 있다.
# 단, 고객이 하지 않은 말을 확인해주는 형태("가격이 걸리시는군요")는 금지한다.
HESITATION_HINTS = {
    "SIZE_UNCERTAIN": (
        "사이즈 고민에는 제품 정보의 사이즈 체계와 구매 가능 사이즈 **사실로만** 답합니다. "
        "실측이 필요한 판단은 단정하지 말고 피팅으로 확인하시도록 제안합니다. "
        "고객이 사이즈를 정했다면 같은 조언을 반복하지 말고 다음 걸음을 제안합니다 — "
        "피팅이나 해당 사이즈 확인 요청을 넣어드릴지 여쭙는 것까지가 우리 몫입니다."
    ),
    "PRICE_HESITANT": (
        "가격 이야기가 나오면 가격을 변호하지 말고, 제품 정보에 적힌 소재와 만듦새를 "
        "이야기합니다. 적혀 있지 않은 역사·연혁은 지어내지 않습니다. "
        "고객이 가격을 직접 말하기 전에는 가격 부담을 먼저 언급하지 않습니다."
    ),
}


def generate_integration_reply(
    message,
    conversation_history=None,
    target_product=None,
    owned_assets=None,
    hesitation_type=None,
):
    """통합 계약(/clienteling/reply)의 한 턴 응답을 만든다.

    반환 형식은 engine.generate_reply 와 같다: {"reply", "suggested_action"}
    """
    message = engine._clean_text(message)
    conversation_history = engine._clean_history(conversation_history)

    # 추궁 판정에 쓸 재료를 먼저 계산한다 — 아래 블록 구성이 이 결과에 달려 있다.
    past_user_text = " ".join(
        turn.get("content", "")
        for turn in conversation_history
        if isinstance(turn, dict) and turn.get("role") == "user"
    )
    past_advisor_text = " ".join(
        turn.get("content", "")
        for turn in conversation_history
        if isinstance(turn, dict) and turn.get("role") == "assistant"
    )
    # 이 대화에서 **실제로 언급된** 보유 제품만 추궁 노트에 넘긴다.
    # 전부 넘겼더니, 구매 대화 중 "제 사이즈를 어떻게 아세요?" 라는 추궁에
    # 언급한 적도 없는 Oxford 를 "구매 기록에서 꺼내 안내했다"고 자백했다(3/3).
    # 하지 않은 인출을 자백하는 것도 하지 않은 발언을 지어내는 것과 같은 오류다.
    # 언급 판정은 대상 제품과 겹치지 않는 토큰으로 한다.
    # 라인 이름("Aurelia")으로 판정했더니, 같은 라인의 Derby 를 상담하는 대화에서
    # Oxford 가 언급된 것으로 잘못 세어졌다(3/3). 같은 라인 제품끼리는
    # 구별 토큰("Oxford")이 실제로 나왔을 때만 언급으로 친다.
    past_texts = past_user_text + " " + past_advisor_text
    target_tokens = set()
    if isinstance(target_product, dict):
        target_tokens = {
            t for t in str(target_product.get("name") or "").split() if len(t) >= 2
        }
    mentioned_owned = []
    for a in owned_assets or []:
        if not isinstance(a, dict):
            continue
        name = str(a.get("product_name") or "").strip()
        if not name:
            continue
        distinct = [t for t in name.split() if len(t) >= 2 and t not in target_tokens]
        if name in past_texts or any(t in past_texts for t in distinct):
            mentioned_owned.append({"name": name})
    customer_like = {"owned_products": mentioned_owned}
    challenge_note = build_source_challenge_note(message, customer_like, past_user_text)

    blocks = []
    # 고객이 대상 제품이 아닌 다른 제품을 말씀하셨으면, 대상 제품 정보를
    # 아예 가리고 불일치 사실을 준다. 규칙("옮겨 쓰지 마라")만으로는 mini 가
    # 3/3 옮겨 썼다. 없으면 인용할 수 없다.
    unknown_tokens = _unknown_product_tokens(message, target_product, owned_assets)
    if unknown_tokens:
        blocks.append(
            "# 대상 제품 불일치 (코드가 판정했습니다)\n"
            f"고객이 말씀하신 제품({', '.join(unknown_tokens)})은 우리가 정보를"
            " 가진 제품이 아닙니다. 다른 제품의 사이즈·수치·가격을 이 제품에"
            " 옮겨 쓰지 않습니다. 그 제품에 대해 아는 것이 없다고 솔직히 말하고,"
            " 확인 요청을 넣어드릴지 여쭙는 것까지가 이번 답의 몫입니다."
        )
    else:
        product_block = _product_block(target_product)
        if product_block:
            blocks.append(product_block)
    # 추궁 턴에 이 대화에서 언급된 적 없는 보유 제품이 프롬프트에 있으면,
    # 모델이 설명거리를 찾다가 그것을 집는다 — 노트에서 빼는 것만으로는 부족했다
    # (3/3 재발). 없으면 인용할 수 없다. 블록째 가린다.
    hide_owned = bool(challenge_note) and not mentioned_owned
    owned_block = "" if hide_owned else _owned_block(owned_assets, message)
    if owned_block:
        blocks.append(owned_block)
    hint = HESITATION_HINTS.get(str(hesitation_type or ""))
    if hint:
        blocks.append("# 이번 상담에서 주의할 것\n" + hint)

    # 맨 뒤 자리가 가장 힘이 세다 — FINAL_CHECK 를 진짜 마지막에 둔다 (MCM 경로와 동일).
    user_content = message
    if blocks:
        user_content += "\n\n" + "\n\n".join(blocks)
    user_content += "\n" + engine.FINAL_CHECK

    # 단, 두 장면은 FINAL_CHECK 보다도 뒤에 놓는다 (MCM 경로에서 배운 순서 그대로).
    #
    # 출처 추궁 — 이 프로젝트에서 가장 중요한 장면. 출력 점검이 맨 뒤에 있으면
    # "제안으로 끝내라"가 이기면서 '원치 않으시면 더 드리지 않겠습니다'가 사라진다.
    # 실제로 통합 모드 손 테스트에서 추궁 직후에 "수선 접수를 도와드릴 수 있습니다"
    # 가 붙어 나왔다 — 경계심을 표한 고객에게 그 정보로 영업을 이어간 것이다.
    if challenge_note:
        user_content += challenge_note
        if not mentioned_owned:
            # 코드가 아는 사실: 이 대화에서 구매 기록의 제품을 꺼낸 적이 없다.
            # 이걸 안 적어주면 모델이 "출처를 밝혀라"에 맞추려고 기록을 발명한다 —
            # "구매 기록에 38 사이즈를 선택하신 적이 있습니다"(3/3, 그런 기록 없음).
            user_content += (
                "\n\n추가 사실 (코드가 판정했습니다): 이 대화에서 우리는 구매 기록을"
                " 꺼낸 적이 **없습니다.** 출처로 구매 기록을 대지 않습니다."
                " 우리가 말한 것은 부티크의 구매 가능 정보와 고객님이 직접 하신"
                " 말씀뿐입니다. 고객님이 말씀하신 것을 두고 안내드렸을 뿐, 그 외의"
                " 개인 정보를 알고 있지 않다고 사실대로 답합니다."
            )
        # mini 가 4단계(통제권)를 2/2 빠뜨렸다. 마지막 문장 지시를 한 번 더,
        # 진짜 맨 뒤에 놓는다. 사과("불편하셨다면 죄송합니다")는 통제권이 아니다.
        user_content += (
            "\n\n답의 마지막 문장은 반드시, 원치 않으시면 이런 안내를"
            " 더 드리지 않겠다는 뜻이어야 합니다. 사과로 대신하지 않습니다."
        )

    # 알 수 없는 입력 — 붙잡을 것이 없으면 모델은 케어 이야기를 지어낸다.
    # 통합 모드에서도 똑같이 재현됐다 ("CU555" 에 케어·수선 추천).
    #
    # build_unclear_note 의 자체 판정은 영문 2글자("CU555" 의 CU)를 단어로 보아
    # 이런 ID 형태를 통과시킨다. 여기서는 언어 감지와 같은 기준으로 더 세게 본다 —
    # 2글자 이상 낱말이 둘 이상이거나 4글자 이상 낱말이 있어야 말로 인정.
    # 조건을 채우면, 항상 걸리는 입력("555")으로 원문 노트 텍스트를 받아 붙인다.
    if _unclear(message):
        user_content += build_unclear_note("555")

    messages = (
        [{"role": "system", "content": INTEGRATION_PROMPT + engine.OUTPUT_FORMAT}]
        + conversation_history
        + [{"role": "user", "content": user_content}]
    )
    return engine._call(messages)
