"""
app/schemas/models.py - Pydantic 스키마
프론트 api/client.js와 필드명 동일하게 맞춤
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# 공통
# ──────────────────────────────────────────────

class WearDetail(BaseModel):
    scratches: int = 0
    cracks: int = 0
    color_fade: bool = False
    hardware_tarnish: bool = False
    lining_damage: bool = False
    strap_wear: bool = False


# ──────────────────────────────────────────────
# GET /api/products/{id}
# ──────────────────────────────────────────────

class ProductResponse(BaseModel):
    product_id: str
    name: str
    brand: str
    category: str
    sub_category: Optional[str] = None
    material: Optional[str] = None
    color: Optional[str] = None
    price_usd: float
    launch_year: Optional[int] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    # 컨디션 (해당 상품을 소유한 경우)
    condition_score: Optional[int] = Field(None, ge=1, le=100)
    condition_grade: Optional[str] = None
    wear_detail: Optional[WearDetail] = None


# ──────────────────────────────────────────────
# POST /api/fingerprint
# ──────────────────────────────────────────────

class FingerprintResponse(BaseModel):
    asset_id: str
    product_id: str
    condition_score: int = Field(..., ge=1, le=100)
    condition_grade: str                    # Mint / Excellent / Good / Fair / Poor
    wear_detail: WearDetail
    summary: str                            # AI1이 생성하는 자연어 상태 요약
    is_new_registration: bool               # True=최초 등록, False=기존과 비교


# ──────────────────────────────────────────────
# POST /api/chat
# ──────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str           # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    user_id: str
    session_id: str
    message: str = Field(..., min_length=1, max_length=2000)
    product_id: Optional[str] = None       # 현재 관심 상품
    history: List[ChatMessage] = []        # 이전 대화 이력 (프론트에서 전달)


class ChatResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    session_id: str
    reply: str
    model_used: str = "gpt-4o"
