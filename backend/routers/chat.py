"""
routers/chat.py - AI 상담 엔드포인트
"""

import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import get_db
from models import Asset, SessionEvent, ChatHistory, Product, MessageRole
from schemas import ConsultRequest, ConsultResponse, AssetOut
import ai_service

router = APIRouter(prefix="/api/chat", tags=["Chat"])


async def _fetch_assets(user_id: str, db: AsyncSession) -> List[AssetOut]:
    stmt = (
        select(Asset)
        .where(Asset.user_id == user_id)
        .options(selectinload(Asset.product))
    )
    result = await db.execute(stmt)
    assets = result.scalars().all()
    return [
        AssetOut(
            asset_id=a.asset_id,
            product_id=a.product_id,
            product_name=a.product.name,
            brand=a.product.brand,
            category=a.product.category,
            purchase_date=a.purchase_date,
            purchase_price=a.purchase_price,
            condition_score=a.condition_score,
            condition_grade=a.condition_grade.value,
            wear_details=a.wear_details,
            last_assessed=a.last_assessed,
            notes=a.notes,
        )
        for a in assets
    ]


async def _fetch_session_history(session_id: str, db: AsyncSession) -> list:
    stmt = (
        select(ChatHistory)
        .where(ChatHistory.session_id == session_id)
        .order_by(ChatHistory.created_at.asc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [{"role": r.role.value, "content": r.content} for r in rows]


async def _fetch_cart_product_name(user_id: str, product_id: str, db: AsyncSession) -> str | None:
    if not product_id:
        return None
    result = await db.execute(select(Product).where(Product.product_id == product_id))
    product = result.scalar_one_or_none()
    return f"{product.brand} {product.name}" if product else None


@router.post("/consult", response_model=ConsultResponse)
async def consult(payload: ConsultRequest, db: AsyncSession = Depends(get_db)):
    """
    AI 상담 엔드포인트.
    - 고객 소유 자산 데이터를 시스템 프롬프트에 주입
    - 세션 대화 이력 유지
    - OpenAI API 호출 후 답변 반환 & DB 저장
    """
    # 1) 컨텍스트 데이터 수집
    assets = await _fetch_assets(payload.user_id, db)
    session_history = await _fetch_session_history(payload.session_id, db)
    cart_product_name = await _fetch_cart_product_name(
        payload.user_id, payload.product_id, db
    ) if payload.include_cart and payload.product_id else None

    # 2) OpenAI 호출
    try:
        result = await ai_service.get_consult_reply(
            user_message=payload.message,
            assets=assets,
            cart_product_name=cart_product_name,
            session_messages=session_history,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    now = datetime.utcnow()

    # 3) 사용자 메시지 저장
    db.add(ChatHistory(
        message_id  = str(uuid.uuid4()),
        user_id     = payload.user_id,
        session_id  = payload.session_id,
        role        = MessageRole.user,
        content     = payload.message,
        created_at  = now,
    ))

    # 4) AI 답변 저장
    db.add(ChatHistory(
        message_id  = str(uuid.uuid4()),
        user_id     = payload.user_id,
        session_id  = payload.session_id,
        role        = MessageRole.assistant,
        content     = result["reply"],
        token_count = result["token_count"],
        model_used  = result["model_used"],
        latency_ms  = result["latency_ms"],
        created_at  = now,
    ))

    await db.flush()

    return ConsultResponse(
        session_id  = payload.session_id,
        reply       = result["reply"],
        model_used  = result["model_used"],
        latency_ms  = result["latency_ms"],
        assets_used = len(assets),
    )
