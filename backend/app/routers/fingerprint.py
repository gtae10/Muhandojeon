"""
app/routers/fingerprint.py
POST /api/fingerprint - 이미지 업로드 → 지문 등록/상태 비교 (AI1 연동)
"""
import uuid
from fastapi import APIRouter, File, Form, UploadFile
from app.schemas.models import FingerprintResponse
from app.services import intent_service

router = APIRouter(tags=["Fingerprint"])


@router.post("/fingerprint", response_model=FingerprintResponse, status_code=201)
async def register_fingerprint(
    product_id: str = Form(..., description="분석할 상품 ID"),
    user_id: str    = Form(..., description="고객 ID"),
    image: UploadFile = File(..., description="상품 이미지 (jpg/png/webp)"),
):
    """
    이미지 업로드 → AI1이 텍스처 분석 → 컨디션 점수 반환.

    multipart/form-data:
        - product_id (string)
        - user_id    (string)
        - image      (file)

    현재: intent_service.analyze_texture() 목업 결과 반환.
    AI1 연동 시: analyze_texture() 내부 로직만 교체.
    """
    image_bytes = await image.read()

    result = await intent_service.analyze_texture(
        image_bytes=image_bytes,
        product_id=product_id,
    )

    return FingerprintResponse(
        asset_id=str(uuid.uuid4()),
        product_id=product_id,
        condition_score=result["condition_score"],
        condition_grade=result["condition_grade"],
        wear_detail=result["wear_detail"],
        summary=result["summary"],
        is_new_registration=True,
    )
