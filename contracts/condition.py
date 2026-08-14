"""컨디션 점수 계약 (백엔드 담당).

엔드포인트: `POST /condition/score`

점수는 0~100(100=신품)이며, **상담 문구가 인용하는 근거**가 되므로 `findings` 는
부위·심각도·소견 문장을 갖춘 형태여야 한다. 컨디션 70 이 케어 권장 임계값이다.

통합 레이어의 목 구현은 `data/processed/customers.json` 에 미리 계산해 둔 결정적 점수를
그대로 반환한다(경과 연수 × 카테고리 마모 계수). 백엔드 실구현은 이미지 기반으로 계산한다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contracts.common import Confidence, Finding, Score100


class ConditionScoreRequest(BaseModel):
    """`POST /condition/score` 요청."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "asset_id": "AS-000031",
                "image_paths": [
                    "data/fingerprints/AS-000031/handle_01.jpg",
                    "data/fingerprints/AS-000031/corner_01.jpg",
                ],
            }
        }
    )

    asset_id: str = Field(description="대상 개체 id")
    image_paths: list[str] = Field(
        default_factory=list,
        description="스캔 이미지 경로. 비어 있으면 마지막 스캔 결과를 반환한다",
    )


class ConditionScoreResponse(BaseModel):
    """`POST /condition/score` 응답."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "asset_id": "AS-000031",
                "score": 71,
                "findings": [
                    {
                        "part": "sole",
                        "severity": "MEDIUM",
                        "note": "앞창 마모 진행, 재밑창 시점 근접",
                    },
                    {"part": "upper", "severity": "LOW", "note": "볼 부분 주름 자연 발생"},
                ],
                "next_service_months": 2,
                "confidence": 0.8,
            }
        }
    )

    asset_id: str
    score: Score100
    findings: list[Finding] = Field(default_factory=list)
    next_service_months: int = Field(
        ge=0, description="컨디션 70 도달까지 남은 개월 수. 0 이면 즉시 케어 권장"
    )
    confidence: Confidence = Field(default=0.8, description="추정 신뢰도")
