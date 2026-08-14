from fastapi import APIRouter

from app.schemas.models import ChatIn, ChatOut
from app.services import clienteling_service

router = APIRouter()


@router.post("", response_model=ChatOut)
async def chat(payload: ChatIn):
    # TODO(AI2 담당): clienteling_service.generate_reply 실제 LLM/RAG 로직으로 교체
    # 스트리밍(SSE)으로 전환하기로 하면 이 엔드포인트를 StreamingResponse로 바꾸고
    # frontend/src/api/client.js의 sendChatMessage도 함께 수정 필요
    reply = clienteling_service.generate_reply(
        product_id=payload.productId, message=payload.message
    )
    return ChatOut(reply=reply)
