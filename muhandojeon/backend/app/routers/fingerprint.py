from fastapi import APIRouter, UploadFile, File, Form

from app.schemas.models import FingerprintOut, WearPoint
from app.services import intent_service

router = APIRouter()


@router.post("", response_model=FingerprintOut)
async def register_fingerprint(
    productId: str = Form(...),
    image: UploadFile = File(...),
):
    image_bytes = await image.read()

    # TODO(AI1 담당): intent_service.analyze_texture 실제 구현으로 교체
    result = intent_service.analyze_texture(product_id=productId, image_bytes=image_bytes)

    return FingerprintOut(
        productId=productId,
        conditionScore=result["conditionScore"],
        wearPoints=[WearPoint(**w) for w in result["wearPoints"]],
    )
