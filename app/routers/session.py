"""`POST /session/advise` — 프론트의 단일 진입점.

폴백이 발생하면 응답 헤더에 `X-Degraded: true` 를 실는다. 화면에는 에러를 노출하지 않되
디버깅은 가능하게 하려는 것이다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.services.orchestrator import Orchestrator, ProductNotFound
from contracts.orchestrator import AdviseRequest, AdviseResponse

router = APIRouter(tags=["Orchestrator"])


@router.post("/session/advise", response_model=AdviseResponse, summary="최종 상담 응답")
def advise(request: AdviseRequest, response: Response) -> AdviseResponse:
    try:
        result = Orchestrator().advise(request)
    except ProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    response.headers["X-Degraded"] = "true" if result.degraded else "false"
    response.headers["X-Owned-Assets-Used"] = "true" if result.owned_assets_used else "false"
    return result
