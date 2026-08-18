"""
app/schemas/models.py - Pydantic 스키마
프론트 api/client.js와 필드명 동일하게 맞춤
계약 호환 스키마 (docs/CONTRACTS.md) 추가
"""
from __future__ import annotations
from datetime import datetime
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
# POST /api/fingerprint  (레거시 폼 업로드 방식)
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
# POST /fingerprint/match  (계약 방식 JSON body)
# ──────────────────────────────────────────────

class FingerprintMatchRequest(BaseModel):
    """POST /fingerprint/match 요청 (계약 형식)."""
    image_path: Optional[str] = Field(
        None, description="data/fingerprints/... 형태의 질의 이미지 경로"
    )
    image_base64: Optional[str] = Field(
        None, description="경로를 못 쓰는 경우의 대안"
    )
    customer_id: Optional[str] = Field(
        None, description="주어지면 해당 고객 소유 개체로 후보를 한정"
    )
    top_k: int = Field(default=3, ge=1, le=20, description="반환할 후보 수")


class FingerprintCandidate(BaseModel):
    """매칭 후보 1건."""
    asset_id: str
    similarity: float = Field(..., ge=0.0, le=1.0)


class FingerprintMatchResponse(BaseModel):
    """POST /fingerprint/match 응답 (계약 형식)."""
    matched_asset_id: Optional[str] = Field(
        None, description="1위 후보. 임계 미달이면 null"
    )
    similarity: float = Field(..., ge=0.0, le=1.0, description="1위 후보 유사도")
    is_match: bool = Field(..., description="similarity >= threshold 여부")
    candidates: List[FingerprintCandidate] = Field(default_factory=list)
    threshold: float = Field(default=0.75, description="판정에 사용한 임계값")


# ──────────────────────────────────────────────
# POST /condition/score  (계약 형식)
# ──────────────────────────────────────────────

class Finding(BaseModel):
    """컨디션 소견 1건."""
    part: str = Field(..., description="부위 (handle/sole/exterior 등)")
    severity: str = Field(..., description="심각도 (LOW/MEDIUM/HIGH)")
    note: str = Field(..., description="사람이 읽는 소견 문장")


class ConditionScoreRequest(BaseModel):
    """POST /condition/score 요청."""
    asset_id: str = Field(..., description="대상 개체 id")
    image_paths: List[str] = Field(
        default_factory=list,
        description="스캔 이미지 경로. 비어 있으면 마지막 스캔 결과를 반환"
    )


class ConditionScoreResponse(BaseModel):
    """POST /condition/score 응답."""
    asset_id: str
    score: int = Field(..., ge=0, le=100, description="0~100 컨디션 점수 (100=신품)")
    findings: List[Finding] = Field(default_factory=list)
    next_service_months: int = Field(
        ..., ge=0, description="컨디션 70 도달까지 남은 개월 수. 0이면 즉시 케어 권장"
    )
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="추정 신뢰도")


# ──────────────────────────────────────────────
# GET /assets/{customer_id}  (계약 형식)
# ──────────────────────────────────────────────

class OwnedAsset(BaseModel):
    """고객이 소유한 개체. 계약의 OwnedAsset 모델."""
    asset_id: str
    customer_id: str
    product_id: str
    product_name: str
    category: str
    purchased_at: datetime
    condition_score: int = Field(..., ge=0, le=100)
    findings: List[Finding] = Field(default_factory=list)
    next_service_months: int = Field(..., ge=0)
    last_scanned_at: Optional[datetime] = None


class CustomerAssetsResponse(BaseModel):
    """GET /assets/{customer_id} 응답 (계약 형식)."""
    customer_id: str
    tier: str = Field(..., description="NEW / ESTABLISHED / VIP")
    assets: List[OwnedAsset] = Field(default_factory=list)


# ──────────────────────────────────────────────
# POST /api/chat  (레거시 + 계약 호환)
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
    # 계약 필드 (docs/BACKEND_INTEGRATION.md)
    cited_asset_ids: List[str] = Field(
        default_factory=list,
        description="상담이 실제로 근거로 삼은 개체 id 목록"
    )
    cta: str = Field(
        default="NONE",
        description="다음 행동 유도 (BOOK_FITTING/VIEW_STOCK/CARE_BOOKING/NONE)"
    )
