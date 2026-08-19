"""오케스트레이터 계약 (통합/데모 담당 = 이 레포).

엔드포인트: `POST /session/advise`

프론트가 호출하는 **단일 진입점**이다. 내부에서 다음 순서로 조합한다.

1. `POST /intent/classify` (AI1)
2. `GET /assets/{customer_id}` (백엔드)
3. 컨디션 점수가 낮거나 서비스 시점이 임박한 자산 우선 정렬 (오케스트레이터)
4. `POST /clienteling/reply` (AI2) — 소유 자산과 컨디션을 컨텍스트로 주입
5. **응답 검증** — `cited_asset_ids` 가 비면 경고 로그 + `owned_assets_used=false`

5번이 제품의 존재 이유를 지키는 관측 지점이다. 소유 자산을 인용하지 않는 상담은
"고객의 물건을 아는 AI"가 아니므로 반드시 드러나야 한다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contracts.assets import CustomerAssetsResponse  # noqa: F401  (문서 생성기 참조용)
from contracts.common import (
    CTA,
    ChatTurn,
    Confidence,
    CustomerTier,
    HesitationType,
    OwnedAsset,
    SessionEvent,
)
from contracts.intent import IntentSignal


class AdviseRequest(BaseModel):
    """`POST /session/advise` 요청."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "customer_id": "CU-0003",
                "target_product_id": "LX-0006",
                "session_events": [
                    {
                        "event_type": "size_guide",
                        "product_id": "LX-0006",
                        "timestamp": "2026-08-14T10:03:20+09:00",
                        "dwell_seconds": 88.5,
                        "meta": {"size": "38.5"},
                    },
                    {
                        "event_type": "size_guide",
                        "product_id": "LX-0006",
                        "timestamp": "2026-08-14T10:05:02+09:00",
                        "dwell_seconds": 61.0,
                        "meta": {"size": "39"},
                    },
                ],
                "strategy_id": "S2",
                "history": [],
            }
        }
    )

    customer_id: str
    target_product_id: str = Field(description="상담 대상 상품 id")
    session_events: list[SessionEvent] = Field(
        default_factory=list,
        description="세션 이벤트. 비우면 인텐트는 NONE 으로 간주하고 일반 제안 모드로 간다",
    )
    strategy_id: str = Field(default="S2", description="상담 전략 id (S1/S2/S3)")
    history: list[ChatTurn] = Field(default_factory=list)
    scenario_id: str | None = Field(
        default=None, description="데모 시나리오 id. 주어지면 고정 시드/캐시 키로 사용한다"
    )


class AssetCitation(BaseModel):
    """상담이 인용한 개체의 요약. 화면에 근거 카드로 렌더한다."""

    asset_id: str
    product_name: str
    condition_score: int
    next_service_months: int
    headline_finding: str | None = Field(
        default=None, description="가장 심각한 소견 문장 (없으면 null)"
    )


class AdviseTraceStep(BaseModel):
    """단계별 실행 기록. `/health/detail` 과 디버깅에 쓴다."""

    step: str = Field(description="단계 이름 (intent/assets/rank/clienteling/validate)")
    adapter: str = Field(description="사용한 어댑터 (예: 'MockIntentAdapter')")
    mode: str = Field(description="mock | http | fallback")
    elapsed_ms: float
    degraded: bool = Field(default=False, description="타임아웃/실패로 폴백했는지")
    detail: str = Field(default="")


class AdviseResponse(BaseModel):
    """`POST /session/advise` 응답. 프론트는 이 하나만 렌더하면 된다."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "request_id": "adv-CU-0003-LX-0006-S2",
                "customer_id": "CU-0003",
                "tier": "ESTABLISHED",
                "hesitation_type": "SIZE_UNCERTAIN",
                "confidence": 0.82,
                "signals": [
                    {
                        "name": "size_guide_repeat",
                        "weight": 0.62,
                        "evidence": "size_guide 2회 조회 (38.5, 39)",
                    }
                ],
                "message": (
                    "2023년에 함께하신 Aurelia Derby와 같은 LAST-AURELIA 라스트입니다. "
                    "현재 컨디션 81점(앞창 마모 진행)이라 재밑창과 함께 피팅을 잡아드릴까요?"
                ),
                "cta": "BOOK_FITTING",
                "cited_asset_ids": ["AS-0010"],
                "citations": [
                    {
                        "asset_id": "AS-0010",
                        "product_name": "Aurelia Derby",
                        "condition_score": 81,
                        "next_service_months": 6,
                        "headline_finding": "앞창 마모 진행",
                    }
                ],
                "owned_assets_used": True,
                "ranked_asset_ids": ["AS-0010", "AS-0011"],
                "strategy_id": "S2",
                "degraded": False,
                "reasoning": "동일 라스트 보유 → 사이즈 불확실 해소.",
                "trace": [
                    {
                        "step": "intent",
                        "adapter": "MockIntentAdapter",
                        "mode": "mock",
                        "elapsed_ms": 1.2,
                        "degraded": False,
                        "detail": "SIZE_UNCERTAIN (0.82)",
                    }
                ],
            }
        }
    )

    request_id: str = Field(description="요청 식별자. 로그 대조용")
    customer_id: str
    tier: CustomerTier
    hesitation_type: HesitationType
    confidence: Confidence
    signals: list[IntentSignal] = Field(default_factory=list)

    message: str = Field(description="고객에게 보여줄 상담 문구")
    cta: CTA = CTA.NONE
    cited_asset_ids: list[str] = Field(default_factory=list)
    citations: list[AssetCitation] = Field(
        default_factory=list, description="인용 개체의 요약. cited_asset_ids 와 순서가 같다"
    )
    owned_assets_used: bool = Field(
        description=(
            "소유 자산을 실제로 인용했는지. **false 면 제품 실패 신호**이며 경고 로그가 남는다. "
            "소유 자산이 아예 없는 신규 고객도 false 가 된다(그때는 no_assets=true)"
        )
    )
    no_assets: bool = Field(default=False, description="고객에게 등록된 개체가 없어서 인용 불가")
    ranked_asset_ids: list[str] = Field(
        default_factory=list, description="컨디션 우선순위로 정렬된 전체 개체 id"
    )
    strategy_id: str = "S2"
    degraded: bool = Field(
        default=False, description="어느 단계든 폴백이 발생했는지. 헤더 X-Degraded 와 동일"
    )
    reasoning: str = ""
    trace: list[AdviseTraceStep] = Field(default_factory=list)


class OwnedAssetRanked(OwnedAsset):
    """정렬 점수를 붙인 개체. 내부 디버깅용이며 프론트 계약에는 포함하지 않는다."""

    priority: float = Field(description="정렬 점수. 클수록 먼저 인용해야 함")
    priority_reason: str = Field(default="")
