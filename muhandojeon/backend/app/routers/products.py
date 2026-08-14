from fastapi import APIRouter, HTTPException

from app.schemas.models import ProductOut, WearPoint

router = APIRouter()

# TODO(풀스택2): 실제 DB 연동 전까지 목업. 프론트 개발 편의를 위해 유지.
_MOCK_PRODUCTS = {
    "demo": ProductOut(
        id="demo",
        name="MCM Aren Backpack",
        purchasedAt="2023-05-12",
        conditionScore=71,
        wearPoints=[WearPoint(part="핸들", severity="임계 근접")],
    )
}


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: str):
    product = _MOCK_PRODUCTS.get(product_id, _MOCK_PRODUCTS["demo"])
    if product is None:
        raise HTTPException(status_code=404, detail="제품을 찾을 수 없습니다")
    return product
