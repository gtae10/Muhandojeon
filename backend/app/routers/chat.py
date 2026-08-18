"""
app/routers/chat.py
POST /api/chat - 상담 메시지 전송 -> AI2 응답 (AI2 연동)

계약 호환 변경사항 (docs/BACKEND_INTEGRATION.md):
    응답에 cited_asset_ids 와 cta 필드를 채운다.
    - cited_asset_ids: 응답 본문에서 AS-[숫자] 패턴 추출 (자동 회수)
    - cta: findings 심각도/카테고리 기반 규칙 결정
    두 필드가 비어 있으면 통합 레이어가 owned_assets_used=false 로 표시한다.

스트리밍 전환 시:
    return StreamingResponse(stream_gen(), media_type="text/event-stream")
    프론트 sendChatMessage도 EventSource 방식으로 함께 수정 필요 (AI2 담당과 조율)
"""

from __future__ import annotations

import re
from typing import List

from fastapi import APIRouter, HTTPException

from app.data.fixture_provider import get_assets_for_customer
from app.schemas.models import ChatRequest, ChatResponse, ChatMessage, OwnedAsset, Finding
from app.services import clienteling_service

router = APIRouter(tags=["Chat"])

# AS-\d{4,} 패턴 (픽스처 ID 형식: AS-0001 ~ AS-9999)
_ASSET_ID_RE = re.compile(r"\bAS-\d{4,}\b")


def _extract_cited_assets(reply_text: str) -> list[str]:
    """
    응답 본문에서 asset_id(AS-XXXX 형식) 를 추출한다.
    AI2 가 cited_asset_ids 를 직접 채워주지 않는 경우의 임시 방편.
    (docs/BACKEND_INTEGRATION.md 참조)
    """
    found = _ASSET_ID_RE.findall(reply_text)
    # 중복 제거, 순서 보존
    seen: set[str] = set()
    result: list[str] = []
    for aid in found:
        if aid not in seen:
            seen.add(aid)
            result.append(aid)
    return result


def _decide_cta(
    cited_ids: list[str],
    assets_raw: list[dict],
    reply_text: str,
) -> str:
    """
    cited_asset_ids 와 자산 findings, 응답 키워드를 기반으로 CTA 결정.

    CTA 우선순위:
        1. CARE_BOOKING  - 인용 자산에 HIGH severity finding 있음
        2. BOOK_FITTING  - 응답에 피팅/방문 관련 키워드
        3. VIEW_STOCK    - 응답에 재고/입고 관련 키워드
        4. NONE          - 기본값
    """
    if cited_ids:
        cited_set = set(cited_ids)
        for a in assets_raw:
            if a.get("asset_id") in cited_set:
                for f in a.get("findings", []):
                    if f.get("severity") == "HIGH":
                        return "CARE_BOOKING"
                # MEDIUM 이상도 케어 권장
                for f in a.get("findings", []):
                    if f.get("severity") in ("MEDIUM", "HIGH"):
                        # 다음 서비스 시점이 임박한 경우에만
                        nsm = a.get("next_service_months", 99)
                        if nsm <= 3:
                            return "CARE_BOOKING"

    lower = reply_text.lower()
    fitting_kw = ["피팅", "방문", "매장", "오프라인", "fitting", "visit"]
    stock_kw = ["재고", "입고", "stock", "available", "품절"]

    if any(kw in lower for kw in fitting_kw):
        return "BOOK_FITTING"
    if any(kw in lower for kw in stock_kw):
        return "VIEW_STOCK"

    return "NONE"


def _build_asset_context_for_service(assets_raw: list[dict]) -> dict | None:
    """
    자산 목록에서 clienteling_service 에 넘길 asset_context dict 생성.
    가장 중요한 자산(condition_score 낮은 것, 즉 케어 필요한 것)을 선택.
    """
    if not assets_raw:
        return None

    # condition_score 낮은 자산 우선 (케어 필요)
    sorted_assets = sorted(
        assets_raw,
        key=lambda a: (a.get("condition_score", 100), a.get("next_service_months", 99))
    )
    primary = sorted_assets[0]

    # wear_detail 형식으로 변환 (clienteling_service 호환)
    from app.schemas.models import WearDetail
    findings = primary.get("findings", [])
    wd = WearDetail(
        scratches=sum(1 for f in findings if f.get("part") in ("exterior", "corner")),
        cracks=sum(1 for f in findings if f.get("severity") == "HIGH"),
        color_fade=any(f.get("part") == "exterior" and "색" in f.get("note", "") for f in findings),
        hardware_tarnish=any(f.get("part") == "hardware" for f in findings),
        lining_damage=any(f.get("part") == "lining" for f in findings),
        strap_wear=any(f.get("part") in ("strap", "handle") for f in findings),
    )

    score = primary.get("condition_score", 75)
    grade = _score_to_grade(score)

    return {
        "asset_id": primary.get("asset_id", ""),
        "product_name": primary.get("product_name", "Unknown"),
        "condition_score": score,
        "condition_grade": grade,
        "wear_detail": wd,
    }


def _score_to_grade(score: int) -> str:
    if score >= 90: return "Mint"
    if score >= 75: return "Excellent"
    if score >= 55: return "Good"
    if score >= 30: return "Fair"
    return "Poor"


@router.post("/api/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    """
    상담 메시지 전송 → AI2가 자산 컨텍스트 기반 응답 생성.

    계약 호환 변경:
        - fixtures 에서 user_id(=customer_id) 기반 자산 조회 후 프롬프트 주입
        - 응답에 cited_asset_ids (본문 추출) + cta (규칙 결정) 필드 채움

    현재: OpenAI GPT-4o 실제 호출 (clienteling_service).
    AI2 연동 시: generate_reply() 내부 로직만 교체.

    확정 필요:
        - 일반 JSON 응답 (현재) vs SSE 스트리밍 응답 (AI2 담당과 조율)
    """
    # 1) 고객 자산 조회 (fixtures 기반)
    assets_raw = get_assets_for_customer(payload.user_id)
    asset_context = _build_asset_context_for_service(assets_raw)

    # 2) AI2 상담 호출
    try:
        result = await clienteling_service.generate_reply(
            message=payload.message,
            history=payload.history,
            asset_context=asset_context,
            product_name=payload.product_id,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    reply_text = result["reply"]

    # 3) cited_asset_ids 추출 (응답 본문에서 AS-XXXX 패턴 회수)
    cited_ids = _extract_cited_assets(reply_text)

    # 자산 ID 목록 문자열도 시스템 주입한 경우 처리
    if not cited_ids and asset_context:
        # asset_context 에서 asset_id 가 직접 언급됐는지 재확인
        aid = asset_context.get("asset_id", "")
        if aid and aid in reply_text:
            cited_ids = [aid]

    # 4) CTA 결정
    cta = _decide_cta(cited_ids, assets_raw, reply_text)

    return ChatResponse(
        session_id=payload.session_id,
        reply=reply_text,
        model_used=result.get("model_used", "gpt-4o"),
        cited_asset_ids=cited_ids,
        cta=cta,
    )
