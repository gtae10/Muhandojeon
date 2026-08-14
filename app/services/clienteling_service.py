"""
app/services/clienteling_service.py
AI2 연동 지점 - 고객 자산 컨텍스트 기반 상담 응답 생성

현재: OpenAI GPT-4o 호출 (실제 동작)
교체 지점: generate_reply() 내부의 OpenAI 호출을 AI2 전용 모델로 교체 가능
"""
import os
import time
from typing import List, Optional
from openai import AsyncOpenAI

from app.schemas.models import ChatMessage, WearDetail

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1024"))


# ──────────────────────────────────────────────
# 프롬프트 빌더
# ──────────────────────────────────────────────

def _build_system_prompt(asset_context: Optional[dict], product_name: Optional[str]) -> str:
    asset_str = "고객 소유 자산 정보 없음."
    if asset_context:
        wd: WearDetail = asset_context.get("wear_detail", WearDetail())
        wear_items = []
        if wd.scratches:        wear_items.append(f"스크래치 {wd.scratches}개")
        if wd.cracks:           wear_items.append(f"크랙 {wd.cracks}개")
        if wd.color_fade:       wear_items.append("색 바램")
        if wd.hardware_tarnish: wear_items.append("하드웨어 변색")
        if wd.lining_damage:    wear_items.append("내부 라이닝 손상")
        if wd.strap_wear:       wear_items.append("스트랩 마모")
        wear_str = " / ".join(wear_items) if wear_items else "특이사항 없음"

        asset_str = (
            f"[고객 소유 자산]\n"
            f"- 상품: {asset_context.get('product_name', '알 수 없음')}\n"
            f"- 컨디션: {asset_context.get('condition_grade')} ({asset_context.get('condition_score')}점)\n"
            f"- 세부 상태: {wear_str}"
        )

    cart_str = f"현재 관심 상품: {product_name}" if product_name else "관심 상품 없음."

    return f"""당신은 세계 최고 수준의 럭셔리 브랜드 개인 어드바이저 AI입니다.
고객의 기존 소유 자산과 물리적 컨디션을 정확히 파악하고, 신규 구매 결정을 도와주는 초개인화 상담을 제공합니다.

{asset_str}

{cart_str}

[상담 원칙]
1. 고객 자산의 컨디션(마모도, 크랙 등)을 분석하여 신규 구매 필요성을 논리적으로 설명하세요.
2. 업그레이드·보완·유지 중 최선의 선택을 구체적 근거와 함께 제시하세요.
3. 럭셔리 브랜드에 걸맞은 고품격 어조를 유지하세요. (과도한 세일즈 압박 금지)
4. 반드시 한국어로, 3~5문장 이내 명료하게 답변하세요.
5. 투자 가치(리세일 가치, 내구성, 희소성)를 자연스럽게 언급하세요."""


# ──────────────────────────────────────────────
# 메인 함수 (AI2 연동 지점)
# ──────────────────────────────────────────────

async def generate_reply(
    message: str,
    history: List[ChatMessage],
    asset_context: Optional[dict] = None,
    product_name: Optional[str] = None,
) -> dict:
    """
    AI2 연동 함수.

    Args:
        message: 현재 사용자 메시지
        history: 이전 대화 이력 [{role, content}, ...]
        asset_context: 고객 소유 자산 컨디션 정보 (intent_service 결과)
        product_name: 현재 관심 상품명

    Returns:
        {"reply": str, "model_used": str}

    TODO (AI2 담당):
        - OpenAI 호출을 AI2 전용 모델 API로 교체 가능
        - 스트리밍이 필요하면 routers/chat.py에서 StreamingResponse로 전환
    """
    system_prompt = _build_system_prompt(asset_context, product_name)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend([{"role": m.role, "content": m.content} for m in history[-20:]])
    messages.append({"role": "user", "content": message})

    response = await _get_client().chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=MAX_TOKENS,
        temperature=0.65,
    )

    return {
        "reply": response.choices[0].message.content.strip(),
        "model_used": MODEL,
    }
