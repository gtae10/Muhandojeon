"""
app/routers/condition.py
POST /condition/score — 계약 경로 (백엔드 담당)

docs/CONTRACTS.md:
    POST /condition/score
    입력: {asset_id, image_paths[]}
    출력: {asset_id, score, findings[], next_service_months, confidence}

docs/BACKEND_INTEGRATION.md:
    - 이미지 없으면 마지막 스캔 결과(픽스처) 반환
    - 이미지 있으면 고전 CV(OpenCV)로 분석
    - next_service_months: 컨디션 70 도달까지 남은 개월 수 (연 8점 감소 가정)
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.models import ConditionScoreRequest, ConditionScoreResponse, Finding
from app.services.condition_service import score_condition

router = APIRouter(tags=["Condition (Contract)"])


@router.post("/condition/score", response_model=ConditionScoreResponse)
async def condition_score(payload: ConditionScoreRequest):
    """
    개체 컨디션 점수 + 부위별 소견 반환 (백엔드 담당).

    - image_paths 있음: OpenCV ORB 기반 마모도 분석
    - image_paths 없음: fixtures/assets.json 의 마지막 스캔 결과 반환

    계약 엔드포인트. CONDITION_ADAPTER=http 환경변수로 통합 레이어와 연결.
    """
    result = await score_condition(
        asset_id=payload.asset_id,
        image_paths=payload.image_paths,
    )

    findings = [
        Finding(
            part=f["part"],
            severity=f["severity"],
            note=f["note"],
        )
        for f in result.get("findings", [])
    ]

    return ConditionScoreResponse(
        asset_id=result["asset_id"],
        score=result["score"],
        findings=findings,
        next_service_months=result["next_service_months"],
        confidence=result["confidence"],
    )
