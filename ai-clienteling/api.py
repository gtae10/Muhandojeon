"""
팀 연동용 API 서버 (개발 단계 5)

실행:
  uvicorn api:app --reload --port 8000

문서 (브라우저에서 직접 눌러볼 수 있음):
  http://127.0.0.1:8000/docs

입출력은 CLAUDE.md 의 "입출력 인터페이스 (팀 합의 스펙)"를 그대로 따른다.
"""

from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
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
