"""
routers/assets.py - 고객 자산 조회 API
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import get_db
from models import Asset, User
from schemas import AssetListResponse, AssetOut

router = APIRouter(prefix="/api/users", tags=["Assets"])


@router.get("/{user_id}/assets", response_model=AssetListResponse)
async def get_user_assets(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    고객 소유 자산 목록 + 컨디션 점수 반환.
    AI 2(RAG) 컨텍스트 제공용.
    """
    # 유저 존재 확인
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")

    # 자산 목록 + 연결 상품 정보 eager load
    stmt = (
        select(Asset)
        .where(Asset.user_id == user_id)
        .options(selectinload(Asset.product))
        .order_by(Asset.purchase_date.desc())
    )
    result = await db.execute(stmt)
    assets = result.scalars().all()

    asset_out = [
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

    return AssetListResponse(user_id=user_id, total=len(asset_out), assets=asset_out)
