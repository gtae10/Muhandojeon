"""
app/routers/products.py
GET /api/products/{id} - 제품 + 컨디션 정보 조회 (목업)
"""
import uuid
from fastapi import APIRouter
from app.schemas.models import ProductResponse, WearDetail

router = APIRouter(tags=["Products"])

# 목업 상품 데이터
_MOCK_PRODUCTS = {
    "lv-neverfull-mm": {
        "product_id": "lv-neverfull-mm",
        "name": "Neverfull MM",
        "brand": "Louis Vuitton",
        "category": "Bag",
        "sub_category": "Tote",
        "material": "Monogram Canvas / Cowhide",
        "color": "Brown",
        "price_usd": 1650.0,
        "launch_year": 2007,
        "description": "Louis Vuitton의 시그니처 토트백. 모노그램 캔버스와 코코넛 레더 트리밍.",
        "image_url": None,
    },
    "chanel-classic-flap": {
        "product_id": "chanel-classic-flap",
        "name": "Classic Flap Medium",
        "brand": "Chanel",
        "category": "Bag",
        "sub_category": "Flap",
        "material": "Lambskin / Gold HW",
        "color": "Black",
        "price_usd": 9500.0,
        "launch_year": 1955,
        "description": "Coco Chanel이 직접 디자인한 클래식 플랩백. 코코넛 메탈 체인 스트랩.",
        "image_url": None,
    },
    "rolex-submariner": {
        "product_id": "rolex-submariner",
        "name": "Submariner Date",
        "brand": "Rolex",
        "category": "Watch",
        "sub_category": "Dive",
        "material": "Oystersteel / Cerachrom",
        "color": "Black",
        "price_usd": 12000.0,
        "launch_year": 1953,
        "description": "다이버용 아이콘 시계. 세라크롬 베젤, 오이스터 케이스.",
        "image_url": None,
    },
}

# 목업 컨디션 (product_id → 컨디션 정보)
_MOCK_CONDITIONS = {
    "lv-neverfull-mm": {
        "condition_score": 72,
        "condition_grade": "Good",
        "wear_detail": WearDetail(scratches=4, cracks=0, color_fade=False, hardware_tarnish=True),
    },
    "chanel-classic-flap": {
        "condition_score": 88,
        "condition_grade": "Excellent",
        "wear_detail": WearDetail(scratches=1, cracks=0),
    },
    "rolex-submariner": {
        "condition_score": 55,
        "condition_grade": "Good",
        "wear_detail": WearDetail(scratches=6, cracks=1, hardware_tarnish=True),
    },
}


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str):
    """
    제품 + 컨디션 정보 조회.
    목업: _MOCK_PRODUCTS / _MOCK_CONDITIONS 딕셔너리로 응답.
    실제 DB 연동 시 SQLAlchemy 쿼리로 교체.
    """
    product = _MOCK_PRODUCTS.get(product_id)
    if not product:
        # 알 수 없는 ID → 제네릭 목업 반환
        product = {
            "product_id": product_id,
            "name": "Unknown Product",
            "brand": "Unknown",
            "category": "Bag",
            "price_usd": 0.0,
        }

    condition = _MOCK_CONDITIONS.get(product_id, {})
    return ProductResponse(**product, **condition)
