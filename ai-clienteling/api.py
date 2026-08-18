"""
팀 연동용 API 서버 (개발 단계 5)

실행:
  uvicorn api:app --reload --port 8102
  (8102 는 통합 레이어의 모듈 포트 배정. app/config.py 의 clienteling_base_url 이 이 포트를 본다)

문서 (브라우저에서 직접 눌러볼 수 있음):
  http://127.0.0.1:8102/docs

입출력은 CLAUDE.md 의 "입출력 인터페이스 (팀 합의 스펙)"를 그대로 따른다.
"""

import re
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

import engine

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
TYPE_WORDS_FOR_CITATION = ("토트", "백팩", "쇼퍼", "크로스바디")

# suggested_action → 통합 레이어의 CTA enum (BOOK_FITTING|VIEW_STOCK|CARE_BOOKING|NONE).
# delivery·staff_connect 에 해당하는 CTA 가 저쪽에 없어 NONE 으로 흘린다.
CTA_FROM_ACTION = {"care_booking": "CARE_BOOKING", "stock_hold": "VIEW_STOCK"}


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


def _assets_to_owned(owned_assets):
    """통합 레이어의 owned_assets 를 우리 owned_products 형식으로 옮긴다.

    condition_score·next_service_months 는 옮기지 않는다.
    프롬프트에 있으면 모델은 결국 인용하고, 그러면 진단서 화법이 나온다.
    (엔진의 _clean_owned 가 한 번 더 거르지만, 입구에서부터 넣지 않는다)
    """
    owned = []
    for asset in owned_assets or []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("product_name") or "").strip()
        if not name:
            continue
        product = {"product_id": asset.get("product_id"), "name": name}
        purchased = str(asset.get("purchased_at") or "")[:7]  # "2023-04-18T…" → "2023-04"
        if purchased:
            product["purchased"] = purchased
        notes = "; ".join(
            str(f.get("note") or "").strip()
            for f in asset.get("findings") or []
            if isinstance(f, dict) and f.get("note")
        )
        if notes:
            # 고객이 상태를 언급하기 전에는 엔진이 프롬프트에서 가린다 (기존 규칙 그대로).
            product["condition"] = {"notes": notes}
        owned.append(product)
    return owned


def _asset_in_text(asset, text, owned_assets):
    """이 텍스트가 이 보유 제품을 가리키는가. 모델 판단이 아니라 문자열 대조다.

    ① 제품 이름(또는 Liz 같은 구별 토큰)이 나왔다
    ② 종류 단어가 나왔고, 그 종류의 보유가 하나뿐이다
       — 고객은 "가지고 있는 쇼퍼백" 처럼 종류로 부른다 (엔진의 종류 매칭과 같은 기준)
    """
    name = str(asset.get("product_name") or "").strip()
    # 구별 토큰은 라인 이름(Liz·Aren·Stark…)만 — 우리 카탈로그에서 라틴 문자다.
    # 한글 토큰(비세토스·스쿨·리버서블…)은 여러 제품이 공유하는 서술어라 쓰면 안 된다.
    # 실제 사고: 사이즈 문의 답변의 "Aren 비세토스 스쿨 토트" 가
    # Liz 쇼퍼의 "비세토스" 토큰에 걸려 엉뚱한 인용(=카드)이 붙었다.
    tokens = [
        t for t in name.split()
        if len(t) >= 2 and t not in GENERIC_TYPE_WORDS and re.search(r"[A-Za-z]", t)
    ]
    if name in text or any(t in text for t in tokens):
        return True
    for word in TYPE_WORDS_FOR_CITATION:
        if word in name and word in text:
            same_kind = [
                a for a in owned_assets
                if isinstance(a, dict) and word in str(a.get("product_name") or "")
            ]
            return len(same_kind) == 1
    return False


def _cited_asset_ids(reply, message, suggested_action, owned_assets):
    """답변이 근거로 삼은 보유 제품을 asset_id 로 되돌린다.

    저쪽의 AS-\\d{6} 정규식은 모델이 문장에 시스템 ID 를 쓴다는 전제인데,
    우리 화법은 ID 를 문장에 쓰지 않으므로 이 필드를 코드가 채워서 넘긴다.
    (필드가 차 있으면 저쪽 정규식은 실행되지 않는다)

    시점 게이트 — 인용은 Frontend 의 근거 카드(컨디션 점수·소견 표시)를 띄우므로,
    프롬프트의 "케어 화제 전에는 컨디션을 가린다" 를 카드에도 적용한다.
    · 고객이 먼저 꺼낸 제품 → 인용한다 (자기 물건 이야기에 근거가 보이는 것은 자연스럽다)
    · 우리가 먼저 꺼낸 제품 → 케어 대화(care_booking)일 때만 인용한다
      (사이즈 문의에 실루엣으로 언급한 보유 제품까지 인용하면,
       묻지도 않은 마모·케어 권장이 카드로 고객 화면에 들어간다)
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
        if customer_brought_it or (we_brought_it and suggested_action == "care_booking"):
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
    """통합 레이어의 폴백 경로. 응답의 reply 는 저쪽 legacy_mapper 가 읽어간다."""
    history = _their_history_to_ours(req.history)
    # 저쪽은 현재 메시지를 history 마지막에도 넣어 보낸다. 겹치면 기록에서 뺀다.
    if history and history[-1]["role"] == "user" and history[-1]["content"] == req.message.strip():
        history = history[:-1]
    try:
        return engine.generate_reply(
            message=req.message,
            customer_id=req.session_id,
            conversation_history=history,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"응답 생성 실패: {e}")


class IntegrationReplyRequest(BaseModel):
    """통합 레이어 계약(contracts/clienteling.py)의 요청. 우리가 쓰는 필드만 받는다.

    target_product 는 아직 쓰지 않는다 — 저쪽 카탈로그(LX-…)와 우리 지식 베이스가
    달라서, 대상 제품 주입은 데이터 정렬이 먼저다. (팀 협의 대상, HANDOFF 참고)
    strategy_id 도 생성에는 쓰지 않는다 — 인용은 전략이 아니라 사실(문장에 나왔는가)로 판정한다.
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


@app.post("/clienteling/reply", response_model=IntegrationReplyResponse)
def clienteling_reply(req: IntegrationReplyRequest):
    """통합 레이어의 계약 경로. 자산 ID 인용까지 채워서 돌려준다."""
    history = _their_history_to_ours(req.history)
    # 마지막 고객 발화가 이번 메시지다. 그 앞까지가 대화 기록.
    if history and history[-1]["role"] == "user":
        message, history = history[-1]["content"], history[:-1]
    else:
        message = "상담 요청"  # 저쪽 폴백 코드와 같은 기본값
    try:
        result = engine.generate_reply(
            message=message,
            customer_id=req.customer_id,
            conversation_history=history,
            # SIZE_UNCERTAIN 같은 계약 라벨은 엔진의 LABEL_MAP 이 옮긴다.
            # 모르는 값은 None 으로 흘러 기본 응대가 된다.
            hesitation_type=req.hesitation_type,
            owned_products=_assets_to_owned(req.owned_assets),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"응답 생성 실패: {e}")
    return IntegrationReplyResponse(
        message=result["reply"],
        cited_asset_ids=_cited_asset_ids(
            result["reply"], message, result["suggested_action"], req.owned_assets
        ),
        cta=CTA_FROM_ACTION.get(result["suggested_action"], "NONE"),
        reasoning=f"AI2 engine / suggested_action={result['suggested_action']}",
    )


# ---------- 개발 확인용 미리보기 ----------
# 실제 근거 카드는 팀 Frontend(CitationCard.jsx)가 그린다. 이 페이지는
# "인용이 있으면 카드가 뜨고, 케어 화제가 아니면 안 뜬다"는 시점 게이트를
# 눈으로 확인하기 위한 것이다. 점수·소견은 자산 데이터에서 오는 것을 재현했다.
# 여러 턴 대화를 지원한다 — 대화 기록은 브라우저(JS)가 들고 매 요청에 보낸다.
# 데모 화면이 아니다 — 팀 연동이 끝나면 지워도 된다.

PREVIEW_HTML = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>자산 카드 미리보기 (개발용)</title>
<style>
  body { font-family: 'Malgun Gothic', sans-serif; max-width: 560px; margin: 40px auto; padding: 0 16px; background: #faf9f7; color: #222; }
  h1 { font-size: 17px; } .note { font-size: 12px; color: #888; margin-bottom: 20px; }
  .preset { margin: 4px 4px 4px 0; padding: 6px 12px; font-size: 13px; cursor: pointer; }
  textarea { width: 100%; height: 60px; font-size: 14px; padding: 8px; box-sizing: border-box; }
  #send { margin-top: 8px; padding: 8px 20px; font-size: 14px; cursor: pointer; }
  .bubble { background: #fff; border: 1px solid #ddd; border-radius: 12px; padding: 14px; margin-top: 6px; font-size: 14px; line-height: 1.6; white-space: pre-wrap; }
  .bubble.user { background: #f0e9dc; border-color: #d9cbb2; }
  #log { margin-bottom: 16px; }
  .label { font-size: 12px; color: #888; margin-top: 18px; }
  .card { border: 1px solid #c9a96a; background: #f7f0e3; border-radius: 12px; padding: 12px 14px; margin-top: 6px; }
  .card .row { display: flex; justify-content: space-between; font-size: 14px; }
  .card .score { color: #a8813d; font-size: 12px; }
  .card .finding { color: #777; font-size: 12px; margin-top: 4px; }
  .card .warn { color: #b3541e; font-size: 12px; margin-top: 4px; }
  .nocard { color: #999; font-size: 13px; margin-top: 6px; }
  .meta { font-size: 12px; color: #aaa; margin-top: 12px; }
</style>
</head>
<body>
<h1>자산 카드 시점 게이트 — 미리보기</h1>
<p class="note">실제 카드는 팀 Frontend 가 그립니다. 이 페이지는 우리 응답의
cited_asset_ids 에 따라 카드가 언제 뜨는지만 재현합니다.<br>
고객 보유 자산(고정): Liz 비세토스 리버서블 쇼퍼 · 컨디션 71점 · 핸들 마모 진행</p>

<button class="preset" onclick="fill('가지고 있는 쇼퍼백이 요즘 좀 낡은 것 같아서요. 손질을 받을 수 있나요?')">케어 질문 (카드 떠야 함)</button>
<button class="preset" onclick="fill('Aren 스쿨 토트에 노트북이 들어갈까요?')">사이즈 질문 (카드 안 떠야 함)</button>
<button class="preset" onclick="resetChat()">대화 새로 시작</button>

<div id="log"></div>

<textarea id="msg" placeholder="고객으로서 자유롭게 물어보세요. Enter 로 전송"></textarea>
<br><button id="send" onclick="send()">보내기</button>

<script>
const ASSET = {
  asset_id: "AS-0001", product_id: "P003",
  product_name: "Liz 비세토스 리버서블 쇼퍼",
  purchased_at: "2023-05-01T00:00:00+09:00",
  condition_score: 71,
  findings: [{part: "handle", severity: "MEDIUM", note: "핸들 마모 진행"}],
  next_service_months: 2
};
let history = [];  // {role: 'customer'|'agent', content} — 매 요청에 통째로 보낸다
const log = document.getElementById('log');
const msgBox = document.getElementById('msg');
function fill(t) { msgBox.value = t; msgBox.focus(); }
function resetChat() { history = []; log.innerHTML = ''; msgBox.value = ''; }
function cardHtml(cited) {
  let h = '<div class="label">인용 근거 (팀 Frontend 의 CitationCard 재현)</div>';
  if (cited) {
    h += '<div class="card"><div class="row"><span>' + ASSET.product_name +
      '</span><span class="score">컨디션 ' + ASSET.condition_score + '점</span></div>' +
      '<div class="finding">' + ASSET.findings[0].note + '</div>' +
      '<div class="warn">' + ASSET.next_service_months + '개월 내 케어 권장</div></div>';
  } else {
    h += '<div class="nocard">인용 없음 → 카드가 뜨지 않습니다. 케어 화제가 아니면 가립니다.</div>';
  }
  return h;
}
async function send() {
  const text = msgBox.value.trim();
  if (!text) return;
  msgBox.value = '';
  history.push({role: 'customer', content: text});
  log.innerHTML += '<div class="label">고객</div><div class="bubble user">' + text + '</div>';
  const wait = document.createElement('p');
  wait.className = 'nocard'; wait.textContent = '답변 생성 중…';
  log.appendChild(wait);
  wait.scrollIntoView();
  try {
    const res = await fetch('/clienteling/reply', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        customer_id: 'CU-0007', hesitation_type: 'NONE',
        owned_assets: [ASSET], strategy_id: 'S2', history: history
      })
    });
    const body = await res.json();
    wait.remove();
    history.push({role: 'agent', content: body.message});
    log.innerHTML += '<div class="label">어드바이저</div><div class="bubble">' + body.message + '</div>' +
      cardHtml((body.cited_asset_ids || []).includes(ASSET.asset_id)) +
      '<div class="meta">cited_asset_ids: ' + JSON.stringify(body.cited_asset_ids) +
      ' · cta: ' + body.cta + '</div>';
  } catch (e) {
    wait.textContent = '요청 실패 — 서버가 켜져 있는지 확인해 주세요. (' + e + ')';
    history.pop();  // 실패한 발화는 기록에서 되돌린다
  }
  log.lastElementChild.scrollIntoView();
}
msgBox.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
});
</script>
</body>
</html>"""


@app.get("/preview", include_in_schema=False)
def preview():
    """개발 확인용 — 자산 카드 시점 게이트를 브라우저에서 눈으로 확인한다."""
    return HTMLResponse(PREVIEW_HTML)
