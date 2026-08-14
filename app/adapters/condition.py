"""컨디션 점수 어댑터 (백엔드).

**대회 제공 API 에 비전 모델이 없다(확정).** 그래서 목 구현은 이미지를 보지 않는다 —
`asset_id` 로 픽스처의 컨디션 점수와 findings 를 그대로 반환한다. `image_paths` 가 와도 무시하고
그 사실을 상태에 남긴다(조용히 다른 값을 내지 않는다).

이미지 기반 실시간 채점은 **백엔드 담당이 고전 CV(OpenCV)로 구현할 예정**이며 계약
(`POST /condition/score` 의 입출력)은 그대로 유지된다. 즉 이 어댑터를 `http` 로 전환하는 것만으로
교체된다.
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
    """픽스처의 컨디션 값을 반환한다(이미지 미사용)."""

    def __init__(self, store: DataStore | None = None) -> None:
        super().__init__(
            module="condition", mode="mock", target="fixtures/assets.json (이미지 미사용)"
        )
        self.store = store or get_store()

    def score(self, request: ConditionScoreRequest) -> ConditionScoreResponse:
        started = time.perf_counter()
        asset = self.store.asset(request.asset_id)
        elapsed = (time.perf_counter() - started) * 1000
        if asset is None:
            self.status.record_failure(elapsed, f"미등록 개체: {request.asset_id}")
            raise UpstreamError(f"개체를 찾을 수 없다: {request.asset_id}")
        # 비전 모델이 없으므로 이미지는 채점에 쓰지 않는다. 왔다는 사실만 상태에 남긴다.
        ignored = f" (이미지 {len(request.image_paths)}장 무시)" if request.image_paths else ""
        self.status.record_success(elapsed, f"{asset.condition_score}점{ignored}")
        return ConditionScoreResponse(
            asset_id=asset.asset_id,
            score=asset.condition_score,
            findings=asset.findings,
            next_service_months=asset.next_service_months,
            confidence=0.8,
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
