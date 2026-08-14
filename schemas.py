"""
schemas.py - Pydantic Request / Response 스키마
"""

from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, EmailStr


# ──────────────────────────────────────────────
# Wear Details sub-schema
# ──────────────────────────────────────────────

class WearDetails(BaseModel):
    scratches: int = Field(0, ge=0, description="스크래치 개수")
    cracks: int    = Field(0, ge=0, description="크랙 개수")
    color_fade: bool = False
    hardware_tarnish: bool = False
    lining_damage: bool = False
    strap_wear: bool = False
    extra: Optional[Dict[str, Any]] = None


# ──────────────────────────────────────────────
# Asset
# ──────────────────────────────────────────────

class AssetOut(BaseModel):
    asset_id: str
    product_id: str
    product_name: str
    brand: str
    category: str
    purchase_date: datetime
    purchase_price: Optional[float]
    condition_score: int
    condition_grade: str
    wear_details: Optional[WearDetails]
    last_assessed: datetime
    notes: Optional[str]

    model_config = {"from_attributes": True}


class AssetListResponse(BaseModel):
    user_id: str
    total: int
    assets: List[AssetOut]


# ──────────────────────────────────────────────
# Session Event
# ──────────────────────────────────────────────

class EventLogRequest(BaseModel):
    user_id: str
    session_id: str
    product_id: Optional[str] = None
    event_type: str = Field(..., pattern="^(view|add_to_cart|remove_from_cart|purchase|abandon)$")
    duration_sec: Optional[float] = None
    device: Optional[str] = None
    referrer: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None


class EventLogResponse(BaseModel):
    event_id: str
    status: str = "logged"


# ──────────────────────────────────────────────
# Chat / Consult
# ──────────────────────────────────────────────

class ConsultRequest(BaseModel):
    user_id: str
    session_id: str
    message: str = Field(..., min_length=1, max_length=2000)
    product_id: Optional[str] = Field(None, description="현재 조회 중인 상품 (망설임 컨텍스트)")
    include_cart: bool = Field(True, description="장바구니 컨텍스트 포함 여부")


class ConsultResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    session_id: str
    reply: str
    model_used: str
    latency_ms: int
    assets_used: int = Field(..., description="컨텍스트에 포함된 자산 수")


# ──────────────────────────────────────────────
# User (간단 조회용)
# ──────────────────────────────────────────────

class UserOut(BaseModel):
    user_id: str
    name: str
    email: str
    tier: str
    country: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
