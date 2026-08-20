"""모듈 엔드포인트 그대로 노출 — 팀원 모듈이 없어도 프론트가 붙을 수 있게.

계약(`docs/CONTRACTS.md`)의 5개 엔드포인트를 이 서버가 그대로 제공한다. 기본은 목이고,
`INTENT_ADAPTER=http` 처럼 모듈별로 전환하면 이 경로가 그대로 실서버로 프록시된다.
프론트는 어느 쪽인지 몰라도 된다.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.adapters.assets import fallback_assets
from app.adapters.base import UpstreamError
from app.adapters.clienteling import fallback_clienteling
from app.adapters.intent import fallback_intent
from app.adapters.registry import (
    get_asset_adapter,
    get_clienteling_adapter,
    get_condition_adapter,
    get_fingerprint_adapter,
    get_intent_adapter,
)
from app.clienteling_rules import build_opening
from contracts.assets import CustomerAssetsResponse
from contracts.clienteling import (
    ClientelingOutreachRequest,
    ClientelingOutreachResponse,
    ClientelingReplyRequest,
    ClientelingReplyResponse,
)
from contracts.condition import ConditionScoreRequest, ConditionScoreResponse
from contracts.fingerprint import FingerprintMatchRequest, FingerprintMatchResponse
from contracts.intent import IntentClassifyRequest, IntentClassifyResponse

router = APIRouter(tags=["Modules"])


def _degraded(response: Response, value: bool) -> None:
    response.headers["X-Degraded"] = "true" if value else "false"


@router.post("/intent/classify", response_model=IntentClassifyResponse, summary="망설임 분류 (AI1)")
def intent_classify(request: IntentClassifyRequest, response: Response) -> IntentClassifyResponse:
    try:
        result = get_intent_adapter().classify(request)
        _degraded(response, False)
        return result
    except UpstreamError:
        _degraded(response, True)
        return fallback_intent(request)


@router.post(
    "/clienteling/reply", response_model=ClientelingReplyResponse, summary="상담 생성 (AI2)"
)
def clienteling_reply(
    request: ClientelingReplyRequest, response: Response
) -> ClientelingReplyResponse:
    try:
        result = get_clienteling_adapter().reply(request)
        _degraded(response, False)
        return result
    except UpstreamError:
        _degraded(response, True)
        return fallback_clienteling(request)


@router.post(
    "/clienteling/outreach",
    response_model=ClientelingOutreachResponse,
    summary="선제 오프닝 (AI2)",
)
def clienteling_outreach(
    request: ClientelingOutreachRequest, response: Response
) -> ClientelingOutreachResponse:
    """어드바이저가 먼저 건네는 첫 마디. 계기가 없으면 `message: null` — 화면은 아무것도
    띄우지 않는다. 업스트림 실패 시 결정적 템플릿 오프닝으로 대체한다."""
    try:
        result = get_clienteling_adapter().outreach(request)
        _degraded(response, False)
        return result
    except UpstreamError:
        _degraded(response, True)
        return build_opening(request)


@router.get(
    "/assets/{customer_id}",
    response_model=CustomerAssetsResponse,
    summary="소유 개체 조회 (백엔드)",
)
def customer_assets(customer_id: str, response: Response) -> CustomerAssetsResponse:
    try:
        result = get_asset_adapter().assets(customer_id)
        _degraded(response, False)
        return result
    except UpstreamError:
        fallback = fallback_assets(customer_id)
        if not fallback.assets:
            raise HTTPException(
                status_code=404, detail=f"고객을 찾을 수 없다: {customer_id}"
            ) from None
        _degraded(response, True)
        return fallback


@router.post(
    "/fingerprint/match", response_model=FingerprintMatchResponse, summary="개체 지문 매칭 (백엔드)"
)
def fingerprint_match(
    request: FingerprintMatchRequest, response: Response
) -> FingerprintMatchResponse:
    try:
        result = get_fingerprint_adapter().match(request)
        _degraded(response, False)
        return result
    except UpstreamError:
        # 지문 매칭은 대체할 사실이 없다. 화면이 깨지지 않게 no-match 로 응답하고 헤더로 표시한다.
        _degraded(response, True)
        return FingerprintMatchResponse(
            matched_asset_id=None,
            similarity=0.0,
            is_match=False,
            candidates=[],
            threshold=0.75,
        )


@router.post(
    "/condition/score", response_model=ConditionScoreResponse, summary="컨디션 점수 (백엔드)"
)
def condition_score(request: ConditionScoreRequest, response: Response) -> ConditionScoreResponse:
    try:
        result = get_condition_adapter().score(request)
        _degraded(response, False)
        return result
    except UpstreamError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
