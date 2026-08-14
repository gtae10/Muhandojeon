"""데모 시나리오 실행 엔드포인트 — 발표에서 버튼 하나로 재생한다.

`POST /demo/scenarios/{id}/run` 은 시나리오의 고정 입력으로 오케스트레이터를 태우고,
`expect` 블록 검증 결과까지 함께 돌려준다. 발표 직전 리허설에 그대로 쓴다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from app.demo import build_request, check_expectations, load_scenarios, pick_session
from app.services.orchestrator import Orchestrator, ProductNotFound

router = APIRouter(tags=["Demo"])


@router.get("/demo/scenarios", summary="데모 시나리오 목록")
def scenarios() -> dict[str, Any]:
    items = load_scenarios()
    return {
        "total": len(items),
        "items": [
            {
                **s.as_dict(),
                "session_id": (lambda rec: rec.session_id if rec else None)(pick_session(s)),
            }
            for s in items.values()
        ],
    }


@router.post("/demo/scenarios/{scenario_id}/run", summary="시나리오 실행 + 기대값 검증")
def run_scenario(scenario_id: str, response: Response) -> dict[str, Any]:
    scenario = load_scenarios().get(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"시나리오를 찾을 수 없다: {scenario_id}")
    request = build_request(scenario)
    try:
        result = Orchestrator().advise(request)
    except ProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    problems = check_expectations(scenario, result)
    response.headers["X-Degraded"] = "true" if result.degraded else "false"
    response.headers["X-Demo-Check"] = "pass" if not problems else "fail"
    return {
        "scenario": scenario.as_dict(),
        "session_id": (lambda rec: rec.session_id if rec else None)(pick_session(scenario)),
        "response": result.model_dump(mode="json"),
        "check": {"passed": not problems, "problems": problems},
    }
