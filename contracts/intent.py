"""AI 1 — 인텐트/망설임 분류 계약.

엔드포인트: `POST /intent/classify`
담당: AI1 팀원. 학습 데이터는 `exports/intent_trainset.parquet` (세션 시퀀스 + 라벨, 8:2 분할).

구현 측 요구사항
    - 입력 세션 이벤트는 시간 순서가 보장되지 않는다. 필요하면 직접 정렬한다.
    - 라벨을 못 정하겠으면 `NONE` + 낮은 confidence 를 반환한다. 예외를 던지지 않는다.
    - `signals` 는 대시보드에 근거로 노출되므로 사람이 읽을 수 있어야 한다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contracts.common import Confidence, HesitationType, SessionEvent


class IntentSignal(BaseModel):
    """분류 근거 1건."""

    name: str = Field(description="신호 이름 (예: 'size_guide_repeat')")
    weight: float = Field(description="기여도. 양수=해당 라벨 지지, 음수=반대")
    evidence: str = Field(description="사람이 읽는 근거 문장 (예: 'size_guide 3회 조회')")


class IntentClassifyRequest(BaseModel):
    """`POST /intent/classify` 요청."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "customer_id": "CU-0007",
                "session_events": [
                    {
                        "event_type": "view_product",
                        "product_id": "LX-0012",
                        "timestamp": "2026-08-14T10:02:11+09:00",
                        "dwell_seconds": 42.0,
                        "meta": {},
                    },
                    {
                        "event_type": "size_guide",
                        "product_id": "LX-0012",
                        "timestamp": "2026-08-14T10:03:20+09:00",
                        "dwell_seconds": 88.5,
                        "meta": {"size": "38"},
                    },
                    {
                        "event_type": "size_guide",
                        "product_id": "LX-0012",
                        "timestamp": "2026-08-14T10:05:02+09:00",
                        "dwell_seconds": 61.0,
                        "meta": {"size": "38.5"},
                    },
                    {
                        "event_type": "add_to_cart",
                        "product_id": "LX-0012",
                        "timestamp": "2026-08-14T10:06:40+09:00",
                        "dwell_seconds": 5.0,
                        "meta": {},
                    },
                ],
            }
        }
    )

    customer_id: str = Field(description="고객 id")
    session_events: list[SessionEvent] = Field(
        min_length=1, description="세션 이벤트 시퀀스 (시간순 정렬 보장 없음)"
    )


class IntentClassifyResponse(BaseModel):
    """`POST /intent/classify` 응답."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "hesitation_type": "SIZE_UNCERTAIN",
                "confidence": 0.82,
                "signals": [
                    {
                        "name": "size_guide_repeat",
                        "weight": 0.62,
                        "evidence": "size_guide 2회 조회 (38, 38.5)",
                    },
                    {
                        "name": "cart_without_checkout",
                        "weight": 0.2,
                        "evidence": "장바구니 담기 후 결제 진입 없음",
                    },
                ],
            }
        }
    )

    hesitation_type: HesitationType
    confidence: Confidence
    signals: list[IntentSignal] = Field(
        default_factory=list, description="분류 근거. 최소 1건을 권장(대시보드 표시용)"
    )
