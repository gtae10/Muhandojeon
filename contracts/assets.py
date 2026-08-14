"""소유 개체 조회 계약 (백엔드 담당).

엔드포인트: `GET /assets/{customer_id}`

오케스트레이터는 이 응답을 받아 **컨디션 우선순위로 재정렬**한 뒤 AI2 에 넘긴다
(점수가 낮거나 `next_service_months` 가 임박한 개체가 앞으로). 정렬 책임은
오케스트레이터에 있으므로 백엔드는 정렬하지 않아도 된다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contracts.common import CustomerTier, OwnedAsset


class CustomerAssetsResponse(BaseModel):
    """`GET /assets/{customer_id}` 응답."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "customer_id": "CU-0007",
                "tier": "ESTABLISHED",
                "assets": [
                    {
                        "asset_id": "AS-000031",
                        "customer_id": "CU-0007",
                        "product_id": "LX-0004",
                        "product_name": "Aurelia Oxford",
                        "category": "SHOES",
                        "purchased_at": "2023-04-18T00:00:00+09:00",
                        "condition_score": 71,
                        "findings": [
                            {
                                "part": "sole",
                                "severity": "MEDIUM",
                                "note": "앞창 마모 진행, 재밑창 시점 근접",
                            }
                        ],
                        "next_service_months": 2,
                        "last_scanned_at": "2026-07-02T14:20:00+09:00",
                    }
                ],
            }
        }
    )

    customer_id: str
    tier: CustomerTier = Field(description="구매 이력 건수 기반 티어")
    assets: list[OwnedAsset] = Field(default_factory=list, description="소유 개체 목록")
