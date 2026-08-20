"""AI 2 — 클라이언텔링 상담 계약.

엔드포인트: `POST /clienteling/reply`
담당: AI2 팀원. RAG 문서는 `exports/catalog_rag.jsonl`, 고객 컨텍스트는
`exports/customer_context.json` 를 그대로 쓰면 된다.

**하드 요구사항**: `owned_assets` 가 비어 있지 않다면 `cited_asset_ids` 에
최소 1개를 담아야 한다. 오케스트레이터는 인용이 없으면 응답에
`owned_assets_used=false` 를 실어 경고한다(= 제품 실패 신호).
전략 S2(소유 자산 연계형)에서 인용이 비면 그 세션은 실패로 본다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contracts.common import CTA, ChatTurn, HesitationType, OwnedAsset, Product


class ClientelingReplyRequest(BaseModel):
    """`POST /clienteling/reply` 요청."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "customer_id": "CU-0003",
                "hesitation_type": "SIZE_UNCERTAIN",
                "target_product": {
                    "product_id": "LX-0006",
                    "name": "Aurelia Oxford",
                    "category": "SHOES",
                    "collection": "Maison Nord",
                    "material": "패티나 카프 / 굿이어 웰트",
                    "color": "Cognac",
                    "price_krw": 2700000,
                    "size_system": "EU 35-42 / Last: LAST-AURELIA",
                    "available_sizes": ["38.5", "39", "40"],
                    "care_notes": "패티나 유지 위해 왁스는 3개월 간격. 우천 착화 지양",
                    "image_path": "images/placeholder/LX-0006.jpg",
                },
                "owned_assets": [
                    {
                        "asset_id": "AS-0010",
                        "customer_id": "CU-0003",
                        "product_id": "LX-0005",
                        "product_name": "Aurelia Derby",
                        "category": "SHOES",
                        "purchased_at": "2023-04-18T00:00:00+09:00",
                        "condition_score": 81,
                        "findings": [
                            {
                                "part": "sole",
                                "severity": "MEDIUM",
                                "note": "앞창 마모 진행",
                            }
                        ],
                        "next_service_months": 6,
                        "last_scanned_at": "2026-06-05T14:00:00+09:00",
                    }
                ],
                "strategy_id": "S2",
                "history": [
                    {"role": "customer", "content": "38.5가 맞을지 39가 맞을지 모르겠어요."}
                ],
            }
        }
    )

    customer_id: str
    hesitation_type: HesitationType = Field(description="AI1 이 분류한 망설임 유형")
    target_product: Product = Field(description="상담 대상 상품")
    owned_assets: list[OwnedAsset] = Field(
        default_factory=list,
        description="고객 소유 개체 목록. 컨디션 우선순위로 정렬되어 전달된다(앞쪽이 더 중요)",
    )
    strategy_id: str = Field(
        default="S2",
        description="상담 전략 id. `data/strategies.yaml` 참조 (S1 정보제공/S2 자산연계/S3 희소성)",
    )
    history: list[ChatTurn] = Field(default_factory=list, description="직전까지의 대화")


class ClientelingReplyResponse(BaseModel):
    """`POST /clienteling/reply` 응답."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": (
                    "2023년에 함께하신 Aurelia Derby와 같은 LAST-AURELIA 라스트입니다. "
                    "그때 38.5로 맞춰 드렸고 현재 컨디션 81점(앞창 마모 진행)이라, "
                    "같은 38.5가 가장 안정적입니다. 재밑창 예약과 함께 피팅을 잡아드릴까요?"
                ),
                "cited_asset_ids": ["AS-0010"],
                "cta": "BOOK_FITTING",
                "reasoning": "동일 라스트 보유 → 사이즈 불확실 해소. 컨디션 81점 → 케어 동시 제안.",
            }
        }
    )

    message: str = Field(description="고객에게 보여지는 상담 문구 (한국어, 2~4문장)")
    cited_asset_ids: list[str] = Field(
        default_factory=list,
        description="message 가 실제로 근거로 삼은 개체 id. 소유 자산이 있으면 비워두지 않는다",
    )
    cta: CTA = Field(default=CTA.NONE)
    reasoning: str = Field(
        default="", description="내부 로그용 판단 근거. 고객에게 노출하지 않는다"
    )


class ClientelingOutreachRequest(BaseModel):
    """`POST /clienteling/outreach` 요청 — 어드바이저가 먼저 건네는 첫 마디.

    고객이 물어야만 답하는 구조는 헬프봇이다. 케어 임박 자산 같은 **계기**가
    있을 때만 열리고, 계기가 없으면 응답 `message` 가 null 이다 — 화면은 그때
    아무것도 띄우지 않는 것이 맞다.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "customer_id": "CU-0001",
                "hesitation_type": "NONE",
                "owned_assets": [
                    {
                        "asset_id": "AS-0001",
                        "customer_id": "CU-0001",
                        "product_id": "LX-0001",
                        "product_name": "Aurelia Top Handle",
                        "category": "BAG",
                        "purchased_at": "2022-04-16T00:00:00+09:00",
                        "condition_score": 71,
                        "findings": [
                            {
                                "part": "handle",
                                "severity": "MEDIUM",
                                "note": "핸들 표면 마모 진행, 케어 임계 근접",
                            }
                        ],
                        "next_service_months": 1,
                        "last_scanned_at": "2026-07-03T14:20:00+09:00",
                    }
                ],
            }
        }
    )

    customer_id: str
    owned_assets: list[OwnedAsset] = Field(
        default_factory=list,
        description="고객 소유 개체 목록. 컨디션 우선순위로 정렬되어 전달된다(앞쪽이 더 중요)",
    )
    hesitation_type: HesitationType | None = Field(
        default=None, description="세션에서 이미 분류된 망설임 유형이 있으면 함께 전달"
    )


class ClientelingOutreachResponse(BaseModel):
    """`POST /clienteling/outreach` 응답."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": (
                    "2022년에 함께하신 Aurelia Top Handle, 컨디션 71점으로 약 1개월 뒤가 "
                    "케어 권장 시점이에요(핸들 표면 마모 진행, 케어 임계 근접). "
                    "다음 방문 때 케어 예약을 함께 잡아 드릴까요?"
                ),
                "cited_asset_ids": ["AS-0001"],
                "cta": "CARE_BOOKING",
                "reasoning": "케어 임박 자산 AS-0001(1개월) → 선제 케어 제안",
            }
        }
    )

    message: str | None = Field(
        default=None,
        description="첫 인사 문구. null 이면 계기 없음 — 오프닝을 띄우지 않는다 (에러가 아니다)",
    )
    cited_asset_ids: list[str] = Field(
        default_factory=list,
        description="message 가 실제로 근거로 삼은 개체 id (케어 오프닝일 때 채워진다)",
    )
    cta: CTA = Field(default=CTA.NONE)
    reasoning: str = Field(
        default="", description="내부 로그용 판단 근거. 고객에게 노출하지 않는다"
    )
