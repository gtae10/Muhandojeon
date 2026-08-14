"""
app/routers/chat.py
POST /api/chat - 상담 메시지 전송 → AI2 응답 (AI2 연동)

스트리밍 전환 시:
    return StreamingResponse(stream_gen(), media_type="text/event-stream")
    프론트 sendChatMessage도 EventSource 방식으로 함께 수정 필요 (AI2 담당과 조율)
"""
from fastapi import APIRouter, HTTPException
from app.schemas.models import ChatRequest, ChatResponse
from app.services import clienteling_service

router = APIRouter(tags=["Chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    """
    상담 메시지 전송 → AI2가 자산 컨텍스트 기반 응답 생성.

    현재: OpenAI GPT-4o 실제 호출 (clienteling_service).
    AI2 연동 시: generate_reply() 내부 로직만 교체.

    확정 필요:
        - 일반 JSON 응답 (현재) vs SSE 스트리밍 응답 (AI2 담당과 조율)
    """
    try:
        result = await clienteling_service.generate_reply(
            message=payload.message,
            history=payload.history,
            asset_context=None,       # TODO: fingerprint 결과 캐시 또는 DB 조회로 채울 것
            product_name=payload.product_id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    return ChatResponse(
        session_id=payload.session_id,
        reply=result["reply"],
        model_used=result["model_used"],
    )
