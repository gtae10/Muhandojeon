import os
import time
from typing import List, Optional
from openai import AsyncOpenAI
from schemas import AssetOut

_client: Optional[AsyncOpenAI] = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1024"))


# ──────────────────────────────────────────────
# Prompt Builders
# ──────────────────────────────────────────────

def _build_asset_context(assets: List[AssetOut]) -> str:
    if not assets:
        return "고객의 소유 자산 정보 없음."

    lines = ["[고객 소유 자산 목록]"]
    for a in assets:
        wd = a.wear_details
        wear_summary = ""
        if wd:
            items = []
            if wd.scratches:  items.append(f"스크래치 {wd.scratches}개")
            if wd.cracks:     items.append(f"크랙 {wd.cracks}개")
            if wd.color_fade: items.append("색 바램")
            if wd.hardware_tarnish: items.append("하드웨어 변색")
            if wd.lining_damage:    items.append("내부 라이닝 손상")
            if wd.strap_wear:       items.append("스트랩 마모")
            wear_summary = "/ ".join(items) if items else "상태 양호"

        lines.append(
            f"- {a.brand} {a.product_name} ({a.category})"
            f" | 구매일: {a.purchase_date.strftime('%Y-%m')}"
            f" | 컨디션: {a.condition_grade}({a.condition_score}점)"
            f" | 세부: {wear_summary}"
        )
    return "\n".join(lines)


def _build_system_prompt(assets: List[AssetOut], cart_product_name: Optional[str] = None) -> str:
    asset_ctx = _build_asset_context(assets)
    cart_ctx  = f"현재 관심 상품: {cart_product_name}" if cart_product_name else "관심 상품 정보 없음."

    return f"""당신은 세계 최고 수준의 럭셔리 브랜드 개인 어드바이저 AI입니다.
고객의 기존 소유 자산과 물리적 컨디션을 정확히 파악하고, 신규 구매 결정을 도와주는 초개인화 상담을 제공합니다.

{asset_ctx}

{cart_ctx}

[상담 원칙]
1. 고객의 기존 자산 컨디션(마모도, 크랙 등)을 분석하여 신규 구매 필요성을 논리적으로 설명하세요.
2. 업그레이드, 보완, 또는 유지 중 최선의 선택을 구체적 근거와 함께 제시하세요.
3. 럭셔리 브랜드에 걸맞은 고품격 어조를 유지하세요. (과도한 세일즈 압박 금지)
4. 답변은 반드시 한국어로, 3~5문장 이내의 명료한 형태로 제공하세요.
5. 고객의 투자 가치 관점(리세일 가치, 내구성, 희소성)을 자연스럽게 언급하세요."""


# ──────────────────────────────────────────────
# Main Service Function
# ──────────────────────────────────────────────

async def get_consult_reply(
    user_message: str,
    assets: List[AssetOut],
    cart_product_name: Optional[str] = None,
    session_messages: Optional[list] = None,
) -> dict:
    """
    OpenAI Chat Completion 호출.
    session_messages: 이전 대화 이력 [{"role": ..., "content": ...}, ...]
    """
    system_prompt = _build_system_prompt(assets, cart_product_name)

    messages = [{"role": "system", "content": system_prompt}]

    # 이전 대화 이력 주입 (최대 10턴 유지)
    if session_messages:
        messages.extend(session_messages[-20:])  # 최대 20 메시지 = 10턴

    messages.append({"role": "user", "content": user_message})

    t0 = time.perf_counter()
    response = await get_client().chat.completions.create(
        model=MODEL,
        messages=messages,
        max_tokens=MAX_TOKENS,
        temperature=0.65,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    reply      = response.choices[0].message.content.strip()
    token_used = response.usage.completion_tokens

    return {
        "reply":       reply,
        "model_used":  MODEL,
        "latency_ms":  latency_ms,
        "token_count": token_used,
    }


async def classify_hesitation(events: list) -> str:
    """
    행동 이벤트 시퀀스를 기반으로 망설임 수준 분류.
    returns: "low" | "medium" | "high"
    """
    view_count = sum(1 for e in events if e["event_type"] == "view")
    cart_count = sum(1 for e in events if e["event_type"] == "add_to_cart")
    abandon_count = sum(1 for e in events if e["event_type"] == "abandon")

    if abandon_count >= 2 or (view_count >= 3 and cart_count == 0):
        return "high"
    elif cart_count >= 1 and abandon_count >= 1:
        return "medium"
    return "low"
