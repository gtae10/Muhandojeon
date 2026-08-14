"""카탈로그·고객 조회 — 프론트가 화면을 채우기 위한 읽기 전용 편의 엔드포인트.

계약(팀 인터페이스)에는 없지만 데모 화면이 필요로 한다. Phase 2 산출물을 그대로 돌려준다.
이미지는 `/static/images/{product_id}.jpg` 로 서빙된다(원본 해상도 60x80 — 작게 렌더할 것).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.store import get_store
from contracts.common import Product

router = APIRouter(tags=["Catalog"])


@router.get("/catalog", summary="상품 40개 목록")
def catalog(
    category: str | None = Query(default=None, description="카테고리 필터 (BAG/SHOES/...)"),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict[str, Any]:
    store = get_store()
    items = list(store.products.values())
    if category:
        items = [p for p in items if p.category.value == category.upper()]
    return {
        "total": len(items),
        "items": [
            {
                **p.model_dump(mode="json"),
                "image_url": f"/static/{p.image_path}" if p.image_path else None,
            }
            for p in items[:limit]
        ],
    }


@router.get("/catalog/{product_id}", response_model=Product, summary="상품 1건")
def product(product_id: str) -> Product:
    found = get_store().product(product_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"상품을 찾을 수 없다: {product_id}")
    return found


@router.get("/customers", summary="고객 목록 (데모 선택용)")
def customers(
    tier: str | None = Query(default=None, description="NEW/ESTABLISHED/VIP"),
) -> dict[str, Any]:
    store = get_store()
    records = list(store.customers.values())
    if tier:
        records = [c for c in records if c.tier.value == tier.upper()]
    return {
        "total": len(records),
        "items": [
            {
                "customer_id": c.customer_id,
                "display_name": c.display_name,
                "tier": c.tier.value,
                "asset_count": len(c.assets),
                "care_due": sum(1 for a in c.assets if a.next_service_months <= 3),
                "min_condition": min((a.condition_score for a in c.assets), default=None),
            }
            for c in records
        ],
    }


@router.get("/sessions", summary="이탈 세션 목록 (데모 입력용)")
def sessions(
    label: str | None = Query(default=None, description="망설임 라벨 필터"),
) -> dict[str, Any]:
    store = get_store()
    records = list(store.sessions.values())
    if label:
        records = [s for s in records if s.hesitation_label == label.upper()]
    return {
        "total": len(records),
        "items": [
            {
                "session_id": s.session_id,
                "customer_id": s.customer_id,
                "target_product_id": s.target_product_id,
                "hesitation_label": s.hesitation_label,
                "label_confidence": s.label_confidence,
                "event_count": len(s.events),
            }
            for s in records
        ],
    }


@router.get("/sessions/{session_id}", summary="세션 1건 (이벤트 전문)")
def session_detail(session_id: str) -> dict[str, Any]:
    record = get_store().sessions.get(session_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"세션을 찾을 수 없다: {session_id}")
    return {
        "session_id": record.session_id,
        "customer_id": record.customer_id,
        "target_product_id": record.target_product_id,
        "hesitation_label": record.hesitation_label,
        "label_confidence": record.label_confidence,
        "profile": record.profile,
        "signals": record.signals,
        "events": [e.model_dump(mode="json") for e in record.events],
    }
