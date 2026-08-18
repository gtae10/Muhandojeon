"""
app/routers/fingerprint.py
POST /fingerprint/match — 계약 경로 (백엔드 담당)
POST /api/fingerprint   — 레거시 폼 업로드 방식 유지 (AI1 연동)

docs/CONTRACTS.md:
    POST /fingerprint/match
    입력: {image_path?, image_base64?, customer_id?, top_k}
    출력: {matched_asset_id, similarity, is_match, candidates[], threshold}

docs/BACKEND_INTEGRATION.md 레거시 매핑:
    is_new_registration → is_match 반전
    similarity: 기존 개체=0.9, 최초 등록=0.0

스트리밍 전환 시:
    return StreamingResponse(stream_gen(), media_type="text/event-stream")
    프론트 sendChatMessage도 EventSource 방식으로 함께 수정 필요 (AI2 담당과 조율)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.models import (
    FingerprintMatchRequest,
    FingerprintMatchResponse,
    FingerprintCandidate,
    FingerprintResponse,
    WearDetail,
)
from app.services import intent_service
from app.services.fingerprint_service import match_fingerprint

router = APIRouter(tags=["Fingerprint"])


# ──────────────────────────────────────────────
# 계약 경로: POST /fingerprint/match (JSON body)
# ──────────────────────────────────────────────

@router.post("/fingerprint/match", response_model=FingerprintMatchResponse, tags=["Fingerprint (Contract)"])
async def fingerprint_match(payload: FingerprintMatchRequest):
    """
    촬영 이미지를 등록 개체와 대조 (계약 형식).

    입력:
        image_path  또는  image_base64 중 하나는 필수.
        customer_id 주어지면 해당 고객 소유 개체로 후보 한정.

    출력:
        matched_asset_id: 1위 후보 (임계 미달이면 null)
        similarity: 유사도 (0~1)
        is_match: similarity >= 0.75 여부
        candidates: top_k 후보 목록
        threshold: 사용된 임계값

    CONDITION_ADAPTER=http 환경변수로 통합 레이어와 연결.
    """
    if not payload.image_path and not payload.image_base64:
        raise HTTPException(
            status_code=422,
            detail="image_path 또는 image_base64 중 하나는 필수입니다.",
        )

    result = await match_fingerprint(
        image_path=payload.image_path,
        image_base64=payload.image_base64,
        customer_id=payload.customer_id,
        top_k=payload.top_k,
    )

    candidates = [
        FingerprintCandidate(
            asset_id=c["asset_id"],
            similarity=c["similarity"],
        )
        for c in result.get("candidates", [])
    ]

    return FingerprintMatchResponse(
        matched_asset_id=result["matched_asset_id"],
        similarity=result["similarity"],
        is_match=result["is_match"],
        candidates=candidates,
        threshold=result["threshold"],
    )


# ──────────────────────────────────────────────
# 레거시 경로: POST /api/fingerprint (multipart/form-data)
# AI1 연동 지점 — 이미지 업로드 → 지문 등록/상태 비교
# ──────────────────────────────────────────────

@router.post(
    "/api/fingerprint",
    response_model=FingerprintResponse,
    status_code=201,
    tags=["Fingerprint (Legacy)"],
)
async def register_fingerprint(
    product_id: str = Form(..., description="분석할 상품 ID"),
    user_id: str    = Form(..., description="고객 ID"),
    image: UploadFile = File(..., description="상품 이미지 (jpg/png/webp)"),
):
    """
    이미지 업로드 → AI1이 텍스처 분석 → 컨디션 점수 반환 (레거시).

    multipart/form-data:
        - product_id (string)
        - user_id    (string)
        - image      (file)

    현재: intent_service.analyze_texture() 목업 결과 반환.
    AI1 연동 시: analyze_texture() 내부 로직만 교체.

    통합 레이어 매핑:
        is_new_registration=True  → is_match=False (최초 등록)
        is_new_registration=False → is_match=True  (기존 개체와 대조)
        similarity: 기존 개체=0.9, 최초 등록=0.0
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
