"""
팀 연동용 API 서버 (개발 단계 5)

실행:
  uvicorn api:app --reload --port 8102
  (8102 는 통합 레이어의 모듈 포트 배정. app/config.py 의 clienteling_base_url 이 이 포트를 본다)

문서 (브라우저에서 직접 눌러볼 수 있음):
  http://127.0.0.1:8102/docs

입출력은 CLAUDE.md 의 "입출력 인터페이스 (팀 합의 스펙)"를 그대로 따른다.
"""

import json
import re
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

import engine
from prompts.knowledge import (
    ACCEPT_HINTS,
    ADVISOR_CARE_WORDS,
    SOURCE_CHALLENGE_HINTS,
    data_overlay,
    pick_products,
)

# 근거 카드 연속 유지 판정용 케어 어휘 — care_thread_open 어휘에 케어 설명
# 턴에서 흔한 "관리"·"보습" 을 보탠다. (소견 열림 판정에는 쓰지 않는다 —
# "관리가 쉬운 소재" 같은 제품 설명까지 열리면 안 되므로 그쪽은 보수적 유지)
CARE_REPLY_WORDS = ADVISOR_CARE_WORDS + ("관리", "보습")

# 통합 경로("한 메종" 세계관)가 엔진 호출 동안 갈아끼우는 데이터.
# scripts/build_integration_data.py 가 생성한다 — 직접 수정 금지.
# /chat·/outreach 는 이 파일들을 전혀 읽지 않는다 (동결 유지).
_DATA_DIR = Path(__file__).resolve().parent / "data"
INTEGRATION_DATA = {
    "products.json": _DATA_DIR / "integration_catalog.json",
    "stores.json": _DATA_DIR / "integration_stores.json",
    "customers.json": _DATA_DIR / "integration_customers.json",
}

app = FastAPI(
    title="MCM Clienteling Agent (AI 2)",
    description="상담 에이전트 응답 생성 API",
    version="1.0.0",
)


# ---------- 입출력 형식 ----------
# pydantic 의 BaseModel 을 쓰면 형식이 안 맞는 요청을 FastAPI 가 알아서 걸러준다.


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


# 개발 단계 6 — Persona Bot Lab 이 A/B 비교할 응대 전략 버전
Variant = Literal["default", "storytelling", "practical", "control"]


class ChatRequest(BaseModel):
    customer_id: Optional[str] = Field(None, examples=["C001"])
    message: str = Field(..., examples=["노트북이 들어갈까요?"])
    conversation_history: List[Message] = []
    # 우리 값 넷과 팀 계약 라벨 다섯을 모두 받는다.
    # AI 1 은 클릭 로그(세션 행동)로 분류하고 우리 전략은 발화를 전제로 만들어서,
    # 이름을 하나로 통일하는 대신 engine 에서 옮긴다. (knowledge.LABEL_MAP)
    # Backend 는 AI 1 출력을 그대로 넘겨주시면 됩니다. 변환하실 것 없습니다.
    #
    # 2026-08-18 계약 반영: QUICK_EXIT · GENERAL_BROWSE 제거,
    #                       SIZE_UNCERTAIN · STOCK_CONCERN · NONE 추가.
    hesitation_type: Optional[
        Literal[
            "fit", "price", "timing", "comparison",
            "SIZE_UNCERTAIN", "PRICE_HESITANT", "STYLE_DOUBT", "STOCK_CONCERN", "NONE",
        ]
    ] = None
    # Backend 가 CDP 에서 가져온 보유 제품. 주면 더미 데이터보다 우선한다.
    owned_products: Optional[List[dict]] = None
    # 생략하면 default. Persona Bot Lab 에서만 바꿔 쓰면 된다.
    variant: Variant = "default"


class OutreachRequest(BaseModel):
    customer_id: str = Field(..., examples=["C006"])
    owned_products: Optional[List[dict]] = None
    # AI 1 의 행동 분류를 여기서 씁니다. 첫 마디를 무슨 이야기로 열지 고르는 데만 씁니다.
    # 대화 중(/chat)에는 쓰지 않습니다 — 고객이 입을 열면 말한 것이 근거여야 합니다.
    # 생략하면 계기(착장·케어 시점)만으로 엽니다.
    hesitation_type: Optional[
        Literal[
            "SIZE_UNCERTAIN", "PRICE_HESITANT", "STYLE_DOUBT", "STOCK_CONCERN", "NONE"
        ]
    ] = None
    variant: Variant = "default"


class AgentResponse(BaseModel):
    reply: str
    suggested_action: Literal[
        "care_booking", "stock_hold", "delivery", "staff_connect", "none"
    ]


# ---------- 엔드포인트 ----------


@app.get("/", include_in_schema=False)
def root():
    """주소만 치고 들어온 사람을 문서 페이지로 보낸다."""
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    """서버가 살아있는지, 어떤 모델을 쓰는지 확인용."""
    return {"status": "ok", "model": engine.MODEL}


@app.post("/chat", response_model=AgentResponse)
def chat(req: ChatRequest):
    """고객 발화에 대한 답변을 만든다."""
    try:
        return engine.generate_reply(
            message=req.message,
            customer_id=req.customer_id,
            conversation_history=[m.model_dump() for m in req.conversation_history],
            hesitation_type=req.hesitation_type,
            owned_products=req.owned_products,
            variant=req.variant,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"응답 생성 실패: {e}")


@app.post("/outreach", response_model=AgentResponse)
def outreach(req: OutreachRequest):
    """에이전트가 먼저 건네는 첫 메시지를 만든다.

    팀 합의 스펙에는 없는 엔드포인트다. 착장 후 미구매·케어 시점 같은 사건이
    발생했을 때 시스템이 호출하는 용도이며, 이 서비스의 정체성에 해당한다.
    (스펙 추가 필요 — Backend/Frontend 와 협의 대상)
    """
    try:
        return engine.generate_outreach(
            customer_id=req.customer_id,
            owned_products=req.owned_products,
            hesitation_type=req.hesitation_type,
            variant=req.variant,
        )
    except ValueError as e:
        # 400 의 detail 은 **개발자에게 보내는 말**이다.
        # 이 문구를 고객 화면에 그대로 띄우지 말 것.
        # ("착장·조회 기록이 없습니다" 같은 내부 사정을 손님에게 설명하는 꼴이 된다)
        # 먼저 말을 걸 계기가 없으면 화면에는 아무것도 띄우지 않는 것이 맞다.
        # 이 서비스는 사건이 있을 때만 말을 건다.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"응답 생성 실패: {e}")


# ---------- 통합 레이어 연동 (2026-08-18) ----------
# 통합 레이어(app/adapters/clienteling.py 의 HttpClientelingAdapter)는
# /clienteling/reply 를 먼저 치고, 실패하면 /api/chat 으로 폴백한다.
# 우리 합의 스펙(/chat)과 요청·응답 형식이 달라서 여기서 받아 옮긴다.
# 프롬프트·엔진은 건드리지 않는다 — 변환은 전부 이 파일 안에서 끝난다.


# 인용 판정에서 무시할 종류 단어. "쇼퍼" 가 문장에 있다고 그 제품을
# 언급한 것은 아니다 — 구별되는 토큰(Liz, Aren…)이 있어야 인용으로 친다.
GENERIC_TYPE_WORDS = {"토트", "백팩", "쇼퍼", "크로스바디", "백", "미니", "스쿨"}

# 고객은 제품을 종류로 부른다 ("가지고 있는 쇼퍼백이…"). 그 종류의 보유가
# 하나뿐이면 그것을 가리킨 것이다 — 엔진의 종류 매칭 규칙과 같은 기준.
# "백" 은 "백화점" 에 들어 있어 쓰지 않는다.
# 2026-08-18 확장: 통합 카탈로그(18종)의 종류가 늘었다. 옛 목록(가방 4종)만
# 있어서 "탑핸들 백" 대화에서 인용이 안 잡혀 케어 카드가 안 떴다.
# 값은 그 종류가 제품 이름에 나타나는 표기들 — fixture 이름이 영어라서
# ("Aurelia Top Handle") 한국어 종류 단어만으로는 이름 대조가 안 된다.
TYPE_WORDS_FOR_CITATION = {
    "토트": ("토트", "Tote"),
    "백팩": ("백팩", "Backpack"),
    "쇼퍼": ("쇼퍼", "Shopper"),
    "크로스바디": ("크로스바디", "Crossbody"),
    "탑핸들": ("탑핸들", "Top Handle"),
    "숄더백": ("숄더", "Shoulder"),
    "클러치": ("클러치", "Clutch"),
    "구두": ("구두", "Derby", "Oxford"),
    "부츠": ("부츠", "Boot"),
    "시계": ("시계", "Chronograph", "Automatic"),
    "지갑": ("지갑", "Wallet", "Card Holder"),
    "벨트": ("벨트", "Belt"),
}

# suggested_action → 통합 레이어의 CTA enum (BOOK_FITTING|VIEW_STOCK|CARE_BOOKING|NONE).
# delivery·staff_connect 에 해당하는 CTA 가 저쪽에 없어 NONE 으로 흘린다.
CTA_FROM_ACTION = {"care_booking": "CARE_BOOKING", "stock_hold": "VIEW_STOCK"}

# ---------- BOOK_FITTING 승격 (2026-08-19) ----------
# 엔진에는 피팅에 해당하는 액션이 없어 BOOK_FITTING 이 반환되는 경우가 없었다.
# 엔진·/chat 은 동결 유지 — 이 후처리가 NONE 으로 흐를 턴에서만, 답변이 실제로
# 피팅 접수를 제안·확정했을 때 승격한다 (fix_delivery_action 과 같은 계열:
# 코드가 판정만 하고 모델을 다시 부르지 않는다).
# 어휘는 상상이 아니라 프로브(mini·4o × 장면 2 × 3회)에서 수집한 실제 문장 기준.
#   · "피팅 예약을 진행하겠습니다" (4o 수락 턴 3/3)
#   · "매장에서 실착 경험을 도와드릴까요?" (4o 첫 턴)
#   · "매장에 확인 요청을 넣어드릴까요?" — 재고 확인이지 피팅이 아니다.
#     같은 문장 안에 피팅 어휘가 없으므로 안 걸린다 (같은 문장 규칙의 이유).
# 원칙: 오탐 0 필수·놓침 허용 — 놓치면 현행 NONE 과 같아 잃는 게 없다.
FITTING_WORDS = (
    "피팅", "실착", "착화", "신어보", "착용해보", "착용해 보", "입어보",
    # "실측"·"착용감" (2026-08-19 추가): 4o "매장에 실측 확인 요청을
    # 넣어드릴까요?", "착용감을 확인하실 수 있도록 도와드릴까요?" (각 2회 관측),
    # mini "매장에서 실측 후 맞는 사이즈를 추천받으실 수 있도록" — 전부 실제
    # 출력에서 수집. 팀 계약의 BOOK_FITTING 이 "사이즈 상담 예약"이므로 이
    # 제안들도 이 카드가 맞다. "실물"(제품 확인)과는 다른 단어다.
    # 여기까지가 조정 2라운드 — 이후의 새 표현은 기록만 하고 쫓지 않는다.
    "실측", "착용감",
    "fitting", "try on", "try-on",
)
# 접수 어휘 — 여쭘형·확정형의 **행동 동사**만. 권유형("추천드립니다",
# "권장합니다")은 조언이지 접수가 아니고, 명사("예약", "접수")를 단독으로 넣으면
# "피팅 예약이 가능합니다" 같은 정보 문장까지 걸린다. 정보 동사("알려드릴까요",
# "보여드릴까요")도 접수가 아니라 넣지 않는다.
BOOKING_WORDS = (
    "도와드릴까요", "넣어드릴까요", "예약해드릴까요", "예약해 드릴까요",
    "잡아드릴까요", "진행해드릴까요", "접수해드릴까요",
    "도와드리겠습니다", "넣어드리겠습니다", "진행하겠습니다",
    "예약하겠습니다", "접수하겠습니다", "잡아드리겠습니다", "진행해드리겠습니다",
)
# 거절 차단 — 고객이 거절한 턴에는 답변 내용과 무관하게 승격하지 않는다.
# "원하시면 언제든 피팅 예약을 도와드리겠습니다" 가 규칙에 걸려
# 거절 직후에 카드가 뜨는 오탐 방지. 넓게 잡아도 안전하다 —
# 잘못 차단하면 현행 NONE 과 같을 뿐이다. (추궁 턴 인용 차단과 같은 자리)
REFUSAL_HINTS = (
    "아니요", "아니오", "아뇨", "괜찮아요", "괜찮습니다", "다음에", "나중에",
    "안 할", "않을게", "됐어요", "필요 없", "no thanks", "not now", "maybe later",
)


def _fitting_offer_in(text):
    """같은 문장 안에 피팅 어휘와 접수 어휘가 함께 있는가.

    문장 단위로 보는 이유: "착용해보시는 것이 좋습니다. 매장에 확인 요청을
    넣어드릴까요?" 는 피팅 조언 + 재고 확인이지 피팅 접수가 아니다.
    문장을 합쳐서 보면 이런 턴이 전부 오탐이 된다.
    """
    for sentence in re.split(r"[.!?\n]", text or ""):
        if any(f in sentence for f in FITTING_WORDS) and any(
            b in sentence for b in BOOKING_WORDS
        ):
            return True
    return False


def _book_fitting_cta(reply, message, history):
    """이 턴의 cta 를 BOOK_FITTING 으로 승격할지 판정한다. (NONE 턴에서만 호출)

    게이트 3종:
      1. 답변이 같은 문장 안에서 피팅 접수를 제안·확정했다
      2. 직전 어드바이저 발화의 마지막 문장이 피팅 여쭘이고, 이번 발화가
         짧은 수락이다 — 수락 턴의 답변에는 피팅 단어가 빠질 수 있다
         ("접수를 넣어드리겠습니다"). 동의한 턴에 카드가 사라지면 안 된다.
         (근거 카드 연속성 게이트와 같은 패턴 — 대상은 직전 발화에 있다)
      3. 고객 발화가 거절이면 전부 차단
    """
    msg = (message or "").strip()
    if any(h in msg.lower() for h in REFUSAL_HINTS):
        return False
    if _fitting_offer_in(reply):
        return True
    # 수락 연속 승격 — 짧은 수락 판정은 build_continuity_note 와 같은 기준.
    if len(msg) <= 20 and any(h in msg.lower() for h in ACCEPT_HINTS):
        last = ""
        for turn in reversed(history or []):
            if isinstance(turn, dict) and turn.get("role") == "assistant":
                last = str(turn.get("content") or "")
                break
        sentences = [s for s in re.split(r"[.!?\n]", last) if s.strip()]
        if sentences:
            final = sentences[-1]
            # 마지막 문장이 여쭘형("~까요")일 때만 — 이미 확정한 뒤의 "네"는
            # 앞 턴에서 카드가 이미 나갔으므로 다시 붙이지 않는다.
            if "까요" in final and _fitting_offer_in(final):
                return True
    return False


def _their_history_to_ours(history):
    """통합 레이어의 history([{role: 'customer'|…, content}])를 우리 형식으로 옮긴다."""
    ours = []
    for turn in history or []:
        if not isinstance(turn, dict):
            continue
        content = str(turn.get("content") or "").strip()
        if not content:
            continue
        role = "user" if str(turn.get("role")) == "customer" else "assistant"
        ours.append({"role": role, "content": content})
    return ours


def _load_catalog_names():
    """통합 카탈로그 18종의 제품 이름 전부. 인용 토큰의 소속 판정에 쓴다.

    데이터 재생성(build_integration_data.py) 후에는 서버를 다시 띄워야 반영된다.
    """
    try:
        cat = json.loads(
            INTEGRATION_DATA["products.json"].read_text(encoding="utf-8"))
        names = set()
        for p in cat.get("products", []):
            for key in ("name_ko", "name_en"):
                n = str(p.get(key) or "").strip()
                if n:
                    names.add(n)
        return names
    except Exception:
        return set()


_CATALOG_NAMES = _load_catalog_names()


def _asset_in_text(asset, text, owned_assets):
    """이 텍스트가 이 보유 제품을 가리키는가. 모델 판단이 아니라 문자열 대조다.

    ① 제품 이름(또는 Liz 같은 구별 토큰)이 나왔다
    ② 종류 단어가 나왔고, 그 종류의 보유가 하나뿐이다
       — 고객은 "가지고 있는 쇼퍼백" 처럼 종류로 부른다 (엔진의 종류 매칭과 같은 기준)

    토큰을 대조하기 전에 **다른 카탈로그 제품의 전체 이름**을 텍스트에서 지운다
    (2026-08-19). "Aurelia Oxford 38이 맞을까요?" 의 "Aurelia" 가 보유 자산
    Aurelia Derby 의 구별 토큰에 걸려 마모 카드가 뜬 손 테스트 사고.
    그 "Aurelia" 는 Oxford 의 것이지 Derby 의 것이 아니다 — 전체 이름이 있는
    언급은 그 제품이 가져가고, 남은 텍스트로만 토큰을 잡는다.
    (라인 공유 토큰 사고의 형제 — 그때는 충돌 상대가 보유 자산이었고
    이번엔 카탈로그의 다른 제품이라 별도 처리가 필요했다)
    """
    name = str(asset.get("product_name") or "").strip()
    # 구별 토큰은 라인 이름(Liz·Aren·Stark…)만 — 우리 카탈로그에서 라틴 문자다.
    # 한글 토큰(비세토스·스쿨·리버서블…)은 여러 제품이 공유하는 서술어라 쓰면 안 된다.
    # 실제 사고: 사이즈 문의 답변의 "Aren 비세토스 스쿨 토트" 가
    # Liz 쇼퍼의 "비세토스" 토큰에 걸려 엉뚱한 인용(=카드)이 붙었다.
    #
    # 그리고 고객의 **다른 자산과 겹치는 토큰**도 구별 토큰이 아니다 —
    # "Aurelia Top Handle" 답변이 같은 라인의 Aurelia Derby 자산까지 인용해
    # 카드가 두 장 뜬 사고. 겹치면 전체 이름 일치로만 잡는다.
    other_tokens = set()
    for o in owned_assets or []:
        if isinstance(o, dict) and o is not asset:
            other_tokens |= set(str(o.get("product_name") or "").split())
    tokens = [
        t for t in name.split()
        if len(t) >= 2 and t not in GENERIC_TYPE_WORDS
        and re.search(r"[A-Za-z]", t) and t not in other_tokens
    ]
    # 전체 이름 일치는 원문으로, 토큰 일치는 다른 제품 이름을 지운 텍스트로.
    reduced = text
    for other_name in sorted(_CATALOG_NAMES, key=len, reverse=True):
        if other_name != name and other_name not in name and other_name in reduced:
            reduced = reduced.replace(other_name, " ")
    if name in text or any(t in reduced for t in tokens):
        return True
    for word, name_keys in TYPE_WORDS_FOR_CITATION.items():
        if word in text and any(k in name for k in name_keys):
            same_kind = [
                a for a in owned_assets
                if isinstance(a, dict)
                and any(k in str(a.get("product_name") or "") for k in name_keys)
            ]
            return len(same_kind) == 1
    return False


def _cited_asset_ids(reply, message, suggested_action, owned_assets, past_advisor_text=""):
    """답변이 근거로 삼은 보유 제품을 asset_id 로 되돌린다.

    저쪽의 AS-\\d{6} 정규식은 모델이 문장에 시스템 ID 를 쓴다는 전제인데,
    우리 화법은 ID 를 문장에 쓰지 않으므로 이 필드를 코드가 채워서 넘긴다.
    (필드가 차 있으면 저쪽 정규식은 실행되지 않는다)

    시점 게이트 — 인용은 Frontend 의 근거 카드(컨디션 점수·소견 표시)를 띄우므로,
    프롬프트의 "케어 화제 전에는 컨디션을 가린다" 를 카드에도 적용한다.
    · 그 제품이 대화에 나왔고(고객이 꺼냈든 우리가 꺼냈든) 이번 턴이
      케어 대화(care_booking)다 → 인용한다
      (2026-08-19 좁힘 전에는 "고객이 꺼냄"만으로 인용했는데, 보유와 같은
       모델을 새로 사려는 사이즈 문의에도 마모 카드가 떴다. 사이즈 문의에
       실루엣으로 언급한 보유 제품까지 인용하면 묻지도 않은 마모·케어 권장이
       카드로 고객 화면에 들어간다 — 어느 쪽이 꺼냈든 마찬가지다)
    · 연속성 — 앞 어드바이저 턴에서 이미 꺼낸 자산을 이번 답도 이어 말하면
      액션과 무관하게 인용을 유지한다. 케어 오프닝("점검해드렸었죠") 다음 턴이
      접수 제안 없이 설명만 하면 카드가 깜빡이며 사라지던 것을 막는다.
      (처음 꺼내는 턴은 여전히 care_booking 게이트를 통과해야 하므로,
       비케어 화제에 카드가 새로 뜨는 일은 없다)
    """
    cited = []
    for asset in owned_assets or []:
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("asset_id") or "").strip()
        if not asset_id or not str(asset.get("product_name") or "").strip():
            continue
        customer_brought_it = _asset_in_text(asset, message, owned_assets)
        we_brought_it = _asset_in_text(asset, reply, owned_assets)
        # 연속 유지는 **이번 답변이 케어 화제일 때만** (2026-08-19 좁힘).
        # 케어 오프닝 뒤 고객이 구매로 화제를 돌렸는데, 답변이 "Pina와 Aren은
        # 이미 보유하고 계시니…" 라고 이름만 이어 말해도 마모 카드가 남아
        # 있었다 (C006 손 테스트). 케어 설명이 이어지는 턴(케어·관리·보습…)에는
        # 유지되고 — 깜빡임 방지라는 원래 목적 — 화제가 떠난 턴에는 내려간다.
        # 판정 재료는 고객 발화가 아니라 우리 답변(유한한 어휘)이다.
        care_flavored = suggested_action == "care_booking" or any(
            w in reply for w in CARE_REPLY_WORDS
        )
        continued = care_flavored and we_brought_it and _asset_in_text(
            asset, past_advisor_text or "", owned_assets
        )
        # 2026-08-19 좁힘: "고객이 먼저 꺼냄" 단독 인용을 없앴다.
        # 보유 제품과 같은 모델을 **새로 사려는** 화제로 이름을 꺼내도
        # ("Aurelia Derby를 보고 있는데 38이 맞을까요?") 마모 카드가 떴다 —
        # 손 테스트에서 발견. 발화 규칙("제품 이름 등장은 상태 언급이 아니다")을
        # 카드에도 적용한 것. 자기 물건의 상태를 꺼낸 고객은 그 턴이 케어
        # 대화(care_booking)가 되므로 카드는 그대로 뜨고, 케어 화제가 아니면
        # 카드도 없다. 화제가 케어를 떠나면 다음 턴부터 인용이 비는 것도 동일.
        if (
            ((customer_brought_it or we_brought_it)
             and suggested_action == "care_booking")
            or continued
        ):
            cited.append(asset_id)
    return cited


class LegacyChatRequest(BaseModel):
    """폴백 경로 /api/chat 의 요청. (통합 레이어의 legacy_payload 형식)"""

    session_id: Optional[str] = None
    message: str
    product_id: Optional[str] = None
    history: List[dict] = []


@app.post("/api/chat", response_model=AgentResponse)
def legacy_chat(req: LegacyChatRequest):
    """통합 레이어의 폴백 경로. 응답의 reply 는 저쪽 legacy_mapper 가 읽어간다.

    같은 통합 세계관(18종·16명)이어야 하므로 이 경로도 오버레이를 씌운다 —
    안 씌우면 폴백 순간 어드바이저가 6종만 아는 상태로 강등된다.
    """
    history = _their_history_to_ours(req.history)
    # 저쪽은 현재 메시지를 history 마지막에도 넣어 보낸다. 겹치면 기록에서 뺀다.
    if history and history[-1]["role"] == "user" and history[-1]["content"] == req.message.strip():
        history = history[:-1]
    try:
        with data_overlay(INTEGRATION_DATA):
            return engine.generate_reply(
                message=req.message,
                customer_id=req.session_id,
                conversation_history=history,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"응답 생성 실패: {e}")


class IntegrationReplyRequest(BaseModel):
    """통합 레이어 계약(contracts/clienteling.py)의 요청. 우리가 쓰는 필드만 받는다.

    target_product 는 힌트로 쓴다 — 고객 발화에 제품이 없으면 그 이름으로 통합
    카탈로그(18종)에서 제품 상세를 잡는다. 이름이 카탈로그에 있으므로 데이터
    불일치 문제가 없다 (scripts/build_integration_data.py 로 동기화).
    strategy_id 는 생성에 쓰지 않는다 — 인용은 전략이 아니라 사실(문장에 나왔는가)로 판정한다.
    """

    customer_id: Optional[str] = None
    hesitation_type: Optional[str] = None
    target_product: Optional[dict] = None
    owned_assets: List[dict] = []
    strategy_id: Optional[str] = None
    history: List[dict] = []

    # /docs 의 Try it out 에 이 예시가 미리 채워진다. 버튼만 눌러 확인할 수 있게.
    model_config = {
        "json_schema_extra": {
            "example": {
                "customer_id": "CU-0007",
                "hesitation_type": "NONE",
                "owned_assets": [
                    {
                        "asset_id": "AS-0001",
                        "product_id": "P003",
                        "product_name": "Liz 비세토스 리버서블 쇼퍼",
                        "purchased_at": "2023-05-01T00:00:00+09:00",
                        "condition_score": 71,
                        "findings": [
                            {"part": "handle", "severity": "MEDIUM", "note": "핸들 마모 진행"}
                        ],
                        "next_service_months": 2,
                    }
                ],
                "strategy_id": "S2",
                "history": [
                    {
                        "role": "customer",
                        "content": "가지고 있는 쇼퍼백이 요즘 좀 낡은 것 같아서요. 손질을 받을 수 있나요?",
                    }
                ],
            }
        }
    }


class IntegrationReplyResponse(BaseModel):
    message: str
    cited_asset_ids: List[str] = []
    cta: str = "NONE"
    reasoning: str = ""


def _assets_to_owned(owned_assets):
    """통합 계약의 owned_assets → 우리 owned_products.

    condition_score·severity 는 옮기지 않는다 (진단서 화법의 원인 — 엔진의
    OWNED_PRODUCT_FIELDS 화이트리스트가 2차 방어). product_id 는 반드시
    포함한다 — 예산표의 "이미 보유" 표시가 이 값으로 카탈로그와 직결된다.
    """
    owned = []
    for a in owned_assets or []:
        if not isinstance(a, dict):
            continue
        name = str(a.get("product_name") or "").strip()
        if not name:
            continue
        product = {"product_id": a.get("product_id"), "name": name}
        purchased = str(a.get("purchased_at") or "")[:7]
        if purchased:
            product["purchased"] = purchased
        notes = "; ".join(
            str(f.get("note") or "").strip()
            for f in a.get("findings") or []
            if isinstance(f, dict) and f.get("note")
        )
        if notes:
            product["condition"] = {"notes": notes}
        # 케어 이력은 통과시킨다 — 요청 자산이 파일 보유를 덮어쓰는 구조라,
        # 이걸 빠뜨리면 "3년 전 봐드렸었죠" 의 근거가 대화 중에 사라진다.
        if isinstance(a.get("care_history"), list) and a["care_history"]:
            product["care_history"] = a["care_history"]
        owned.append(product)
    return owned


@app.post("/clienteling/reply", response_model=IntegrationReplyResponse)
def clienteling_reply(req: IntegrationReplyRequest):
    """통합 레이어의 계약 경로. 자산 ID 인용까지 채워서 돌려준다.

    2026-08-18 "한 메종" 세계관으로 재설계: 이 경로는 **기존 MCM 엔진을 그대로**
    부르되, 그 호출 동안만 데이터를 18종 카탈로그·16명 고객·확장 재고로
    갈아끼운다 (knowledge.data_overlay). 어드바이저가 전 제품·매장·재고·배송을
    아는 우리 서비스의 전제가 통합 화면에서도 유지된다.
    MCM 데모 경로(/chat·/outreach)는 오버레이를 쓰지 않으므로 그대로다.
    """
    history = _their_history_to_ours(req.history)
    # 마지막 고객 발화가 이번 메시지다. 그 앞까지가 대화 기록.
    if history and history[-1]["role"] == "user":
        message, history = history[-1]["content"], history[:-1]
    else:
        message = "상담 요청"  # 저쪽 폴백 코드와 같은 기본값
    # 빈 owned_assets 는 None 으로 — 엔진의 build_customer 는 owned_products 가
    # 오면 파일 값을 덮어쓰므로, [] 를 그대로 넘기면 통합 고객(CU-xxxx)의
    # 보유 목록이 빈 리스트로 지워진다.
    owned = _assets_to_owned(req.owned_assets) or None
    try:
        with data_overlay(INTEGRATION_DATA):
            # target_product 힌트: 고객 발화·기록에서 제품이 안 잡힐 때만,
            # "지금 보고 계신 제품"이 상세에 잡히게 이름을 매칭 입력에 보탠다.
            pick_hint = ""
            target_name = ""
            if isinstance(req.target_product, dict):
                target_name = str(req.target_product.get("name") or "").strip()
            if target_name:
                convo_text = " ".join(
                    [t.get("content", "") for t in history] + [message]
                )
                if not pick_products(convo_text):
                    pick_hint = target_name
            result = engine.generate_reply(
                message=message,
                customer_id=req.customer_id,
                conversation_history=history,
                hesitation_type=req.hesitation_type,
                owned_products=owned,
                pick_hint=pick_hint,
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"응답 생성 실패: {e}")
    # 출처 추궁 턴에는 인용도 비운다. 인용은 화면의 근거 카드(컨디션 표시)를
    # 띄우는데, "그걸 어떻게 아세요?" 라고 물은 고객에게 마모·케어 권장 카드를
    # 보여주는 것은 경계심에 상태 평가를 얹는 원래 사고의 화면판이다.
    challenged = any(h in message.lower() for h in SOURCE_CHALLENGE_HINTS)
    # BOOK_FITTING 승격은 NONE 으로 흐를 턴에서만 — care_booking·stock_hold 가
    # 고른 카드를 밀어내지 않는다 (카드 충돌 방지).
    cta = CTA_FROM_ACTION.get(result["suggested_action"], "NONE")
    if cta == "NONE" and _book_fitting_cta(result["reply"], message, history):
        cta = "BOOK_FITTING"
    return IntegrationReplyResponse(
        message=result["reply"],
        cited_asset_ids=[] if challenged else _cited_asset_ids(
            result["reply"], message, result["suggested_action"], req.owned_assets,
            past_advisor_text=" ".join(
                t.get("content", "") for t in history
                if isinstance(t, dict) and t.get("role") == "assistant"
            ),
        ),
        cta=cta,
        reasoning=f"AI2 engine / suggested_action={result['suggested_action']}",
    )


class IntegrationOutreachRequest(BaseModel):
    """통합 화면의 '먼저 말 걸기'. 계기가 있어야 열린다.

    "고객이 물어야만 답하는 구조는 헬프봇"이라는 서비스 정체성의 통합판이다.
    계기(장바구니 이탈·케어 시점)는 integration_customers.json 에 있고,
    저쪽 session_events 의 의도적 접점(add_to_cart)에서 변환된다.
    """

    customer_id: str = Field(..., examples=["CU-0001"])
    hesitation_type: Optional[str] = None
    # 오케스트레이터가 이 고객의 자산 목록을 실어주면, 오프닝이 그 자산을
    # 근거로 삼았을 때 인용(→ 근거 카드)이 붙는다. 케어 오프닝의 카드가 여기서 나온다.
    owned_assets: List[dict] = []


@app.post("/clienteling/outreach", response_model=IntegrationReplyResponse)
def clienteling_outreach(req: IntegrationOutreachRequest):
    """통합 세계관에서 어드바이저가 먼저 건네는 첫 마디.

    MCM 데모의 /outreach 는 동결 유지 — 이 경로만 오버레이를 쓴다.
    계기가 없으면 400 (detail 은 개발자용 — 화면에 그대로 띄우지 말 것.
    계기가 없으면 아무것도 안 띄우는 것이 맞다).
    """
    owned = _assets_to_owned(req.owned_assets) or None
    try:
        with data_overlay(INTEGRATION_DATA):
            result = engine.generate_outreach(
                customer_id=req.customer_id,
                owned_products=owned,
                hesitation_type=req.hesitation_type,
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"응답 생성 실패: {e}")
    # 오프닝은 우리가 먼저 꺼내는 턴이므로 인용 게이트의 "케어 대화" 조건으로만
    # 인용한다 — 케어 오프닝("점검해드렸었죠")에는 카드가 뜨고,
    # 장바구니 오프닝(구매 화제)에는 뜨지 않는다. 채팅 턴과 같은 원칙이다.
    return IntegrationReplyResponse(
        message=result["reply"],
        cited_asset_ids=_cited_asset_ids(
            result["reply"], "", result["suggested_action"], req.owned_assets
        ),
        cta=CTA_FROM_ACTION.get(result["suggested_action"], "NONE"),
        reasoning=f"AI2 outreach / suggested_action={result['suggested_action']}",
    )


@app.get("/preview-assets", include_in_schema=False)
def preview_assets():
    """개발 확인용 — preview 페이지가 고객별 자산 목록을 받아간다.

    실제 통합에서는 오케스트레이터가 자기 자산 DB 에서 실어주는 값이다.
    scripts/build_integration_data.py 가 생성한 integration_assets.json 을 그대로 준다.
    """
    path = _DATA_DIR / "integration_assets.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------- 개발 확인용 미리보기 ----------
# 통합 모드 테스트 페이지. 내용은 preview.html (손 테스트 기록 + 직접 채팅).
# 파일로 분리한 이유: 페이지가 커져서 api.py 안 문자열로 두면 코드가 묻힌다.
# 데모 화면이 아니다 — 팀 연동이 끝나면 지워도 된다.


@app.get("/preview", include_in_schema=False)
def preview():
    """개발 확인용 — 통합 모드를 직접 쳐보고, 손 테스트 기록을 본다."""
    page = Path(__file__).parent / "preview.html"
    return HTMLResponse(page.read_text(encoding="utf-8"))
