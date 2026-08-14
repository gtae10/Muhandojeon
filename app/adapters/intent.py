"""인텐트 어댑터 (AI1).

목 구현은 `app/intent_rules.py` 의 규칙 엔진을 그대로 호출한다. Phase 2 의 학습셋 라벨을
만든 것과 **동일한 규칙**이므로, AI1 실구현이 들어오면 "규칙 대비 개선"을 같은 기준으로
비교할 수 있다.
"""

from __future__ import annotations

import time
from typing import Any

from app.adapters.base import AdapterBase
from app.adapters.http_base import HttpAdapterBase
from app.intent_rules import classify
from contracts.common import HesitationType
from contracts.intent import IntentClassifyRequest, IntentClassifyResponse, IntentSignal


class MockIntentAdapter(AdapterBase):
    """규칙 기반 인텐트 분류."""

    def __init__(self) -> None:
        super().__init__(module="intent", mode="mock", target="app.intent_rules.classify")

    def classify(self, request: IntentClassifyRequest) -> IntentClassifyResponse:
        started = time.perf_counter()
        result = classify(request.session_events)
        elapsed = (time.perf_counter() - started) * 1000
        self.status.record_success(
            elapsed, f"{result.hesitation_type.value} ({result.confidence:.2f})"
        )
        return result


def legacy_intent_mapper(raw: Any) -> dict[str, Any]:
    """계약을 아직 안 맞춘 구현의 응답을 흡수한다.

    받아들이는 형태: `intent` / `label` / `hesitation` 키의 라벨, `score` / `confidence` 의 확신도,
    `reasons` / `evidence` 의 근거 문자열 목록.
    """
    if not isinstance(raw, dict):
        raise TypeError(f"dict 가 아님: {type(raw)}")
    label = str(
        raw.get("hesitation_type")
        or raw.get("intent")
        or raw.get("label")
        or raw.get("hesitation")
        or HesitationType.NONE.value
    ).upper()
    if label not in {h.value for h in HesitationType}:
        label = HesitationType.NONE.value
    raw_confidence = raw.get("confidence", raw.get("score", 0.5))
    confidence = float(raw_confidence) if raw_confidence is not None else 0.5
    signals_raw = raw.get("signals") or raw.get("reasons") or raw.get("evidence") or []
    signals: list[dict[str, Any]] = []
    for item in signals_raw:
        if isinstance(item, dict):
            signals.append(
                {
                    "name": str(item.get("name", "signal")),
                    "weight": float(item.get("weight", 0.0)),
                    "evidence": str(item.get("evidence", item.get("detail", ""))),
                }
            )
        else:
            signals.append({"name": "signal", "weight": 0.0, "evidence": str(item)})
    return {
        "hesitation_type": label,
        "confidence": max(0.0, min(1.0, confidence)),
        "signals": signals,
    }


class HttpIntentAdapter(HttpAdapterBase):
    """실제 AI1 서버 호출 (`INTENT_BASE_URL`)."""

    def __init__(self) -> None:
        super().__init__(module="intent")

    def classify(self, request: IntentClassifyRequest) -> IntentClassifyResponse:
        return self.post_model(
            "/intent/classify",
            request.model_dump(mode="json"),
            IntentClassifyResponse,
            legacy_mapper=legacy_intent_mapper,
        )


def fallback_intent(request: IntentClassifyRequest) -> IntentClassifyResponse:
    """업스트림 실패 시 오케스트레이터가 쓰는 폴백. 규칙 엔진 결과를 낮은 확신도로 돌려준다."""
    result = classify(request.session_events)
    return IntentClassifyResponse(
        hesitation_type=result.hesitation_type,
        confidence=round(result.confidence * 0.8, 3),
        signals=[
            *result.signals,
            IntentSignal(
                name="degraded_fallback",
                weight=0.0,
                evidence="AI1 업스트림 응답 실패 → 규칙 엔진 결과로 대체",
            ),
        ],
    )
