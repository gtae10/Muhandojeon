"""컨디션 점수 어댑터 (백엔드).

목 구현은 Phase 2 에서 결정적으로 계산해 둔 점수·소견을 그대로 반환한다(시간 기반 추정치).
실제 이미지 기반 판정은 백엔드 담당의 실구현 몫이다.
"""

from __future__ import annotations

import time
from typing import Any

from app.adapters.assets import _findings_from_wear
from app.adapters.base import AdapterBase, UpstreamError
from app.adapters.http_base import HttpAdapterBase
from app.store import DataStore, get_store
from contracts.condition import ConditionScoreRequest, ConditionScoreResponse

#: 팀 백엔드의 `condition_grade` → 대표 점수(점수가 없을 때만 쓰는 근사치)
GRADE_TO_SCORE: dict[str, int] = {
    "mint": 97,
    "excellent": 88,
    "good": 76,
    "fair": 62,
    "poor": 40,
}


class MockConditionAdapter(AdapterBase):
    """저장된 결정적 컨디션 값을 반환한다."""

    def __init__(self, store: DataStore | None = None) -> None:
        super().__init__(module="condition", mode="mock", target="data/processed/customers.json")
        self.store = store or get_store()

    def score(self, request: ConditionScoreRequest) -> ConditionScoreResponse:
        started = time.perf_counter()
        asset = self.store.asset(request.asset_id)
        elapsed = (time.perf_counter() - started) * 1000
        if asset is None:
            self.status.record_failure(elapsed, f"미등록 개체: {request.asset_id}")
            raise UpstreamError(f"개체를 찾을 수 없다: {request.asset_id}")
        # 스캔 이미지가 주어졌는지에 따라 확신도만 달라진다(점수 자체는 결정적 추정치).
        confidence = 0.85 if request.image_paths else 0.7
        self.status.record_success(elapsed, f"{asset.condition_score}점")
        return ConditionScoreResponse(
            asset_id=asset.asset_id,
            score=asset.condition_score,
            findings=asset.findings,
            next_service_months=asset.next_service_months,
            confidence=confidence,
        )


def legacy_condition_mapper(raw: Any) -> dict[str, Any]:
    """`condition_grade` + `wear_detail` 형태의 응답을 계약으로 옮긴다."""
    if not isinstance(raw, dict):
        raise TypeError(f"dict 가 아님: {type(raw)}")
    score = raw.get("score", raw.get("condition_score"))
    if score is None:
        grade = str(raw.get("condition_grade", "")).strip().lower()
        score = GRADE_TO_SCORE.get(grade, 70)
    score = max(0, min(100, int(score)))
    findings = raw.get("findings")
    if not isinstance(findings, list) or not findings:
        findings = _findings_from_wear(raw.get("wear_detail") or raw.get("wear_details"))
    months = raw.get("next_service_months")
    if months is None:
        # 점수만 있을 때: 70 까지 남은 폭을 연 8점 감소로 환산한다(카테고리 미상이므로 평균값).
        months = 0 if score <= 70 else int((score - 70) / 8.0 * 12)
    return {
        "asset_id": str(raw.get("asset_id", "")),
        "score": score,
        "findings": findings,
        "next_service_months": int(months),
        "confidence": float(raw.get("confidence", 0.7)),
    }


class HttpConditionAdapter(HttpAdapterBase):
    """실제 백엔드 호출 (`CONDITION_BASE_URL`)."""

    def __init__(self) -> None:
        super().__init__(module="condition")

    def score(self, request: ConditionScoreRequest) -> ConditionScoreResponse:
        return self.post_model(
            "/condition/score",
            request.model_dump(mode="json"),
            ConditionScoreResponse,
            legacy_mapper=legacy_condition_mapper,
        )
