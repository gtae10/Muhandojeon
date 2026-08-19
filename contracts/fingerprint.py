"""개체 지문 매칭 계약 (백엔드 담당).

엔드포인트: `POST /fingerprint/match`

촬영한 미세 텍스처 이미지를 등록된 개체와 대조한다. 같은 모델 두 개를 구분해야 하므로
스티치·가죽 결이 선명해야 한다 — 촬영 규약은 `docs/FINGERPRINT_CAPTURE.md`,
등록 CLI 는 `scripts/register_fingerprint.py`.

이미지는 **경로 또는 base64 중 하나**로 전달한다. 통합 레이어는 경로 방식을 쓴다
(데모에서 파일이 로컬에 있고 페이로드를 가볍게 유지하려는 의도적 선택).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts.common import Confidence


class FingerprintMatchRequest(BaseModel):
    """`POST /fingerprint/match` 요청."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "image_path": "data/fingerprints/AS-0001/handle_01.jpg",
                "customer_id": "CU-0001",
                "top_k": 3,
            }
        }
    )

    image_path: str | None = Field(
        default=None, description="`data/fingerprints/...` 형태의 질의 이미지 경로"
    )
    image_base64: str | None = Field(default=None, description="경로를 못 쓰는 경우의 대안")
    customer_id: str | None = Field(
        default=None, description="주어지면 해당 고객 소유 개체로 후보를 한정한다"
    )
    top_k: int = Field(default=3, ge=1, le=20, description="반환할 후보 수")

    @model_validator(mode="after")
    def _require_one_image(self) -> FingerprintMatchRequest:
        if not self.image_path and not self.image_base64:
            raise ValueError("image_path 또는 image_base64 중 하나는 필수")
        return self


class FingerprintCandidate(BaseModel):
    """매칭 후보 1건."""

    asset_id: str
    similarity: Confidence = Field(description="0~1 유사도")


class FingerprintMatchResponse(BaseModel):
    """`POST /fingerprint/match` 응답."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "matched_asset_id": "AS-0001",
                "similarity": 0.94,
                "is_match": True,
                "candidates": [
                    {"asset_id": "AS-0001", "similarity": 0.94},
                    {"asset_id": "AS-0003", "similarity": 0.41},
                ],
                "threshold": 0.75,
            }
        }
    )

    matched_asset_id: str | None = Field(description="1위 후보. 임계 미달이면 null")
    similarity: Confidence = Field(description="1위 후보 유사도")
    is_match: bool = Field(description="similarity >= threshold 여부")
    candidates: list[FingerprintCandidate] = Field(
        default_factory=list, description="상위 top_k 후보 (내림차순)"
    )
    threshold: float = Field(default=0.75, description="판정에 사용한 임계값")
