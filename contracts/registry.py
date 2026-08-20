"""엔드포인트 ↔ 계약 모델 매핑 레지스트리.

`docs/CONTRACTS.md` 와 `contracts/examples/*.json` 은 이 레지스트리에서 **생성**된다
(`make contracts` → `scripts/gen_contracts_doc.py`). 계약을 바꿨으면 문서를 손으로 고치지 말고
모델을 고친 뒤 재생성한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel

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
from contracts.orchestrator import AdviseRequest, AdviseResponse


@dataclass(frozen=True)
class EndpointSpec:
    """한 엔드포인트의 계약 명세."""

    key: str
    method: str
    path: str
    owner: str
    summary: str
    request_model: type[BaseModel] | None
    response_model: type[BaseModel]
    notes: str = ""


ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        key="intent_classify",
        method="POST",
        path="/intent/classify",
        owner="AI1 (인텐트/망설임 분류)",
        summary="세션 이벤트로 구매 망설임 유형을 분류한다",
        request_model=IntentClassifyRequest,
        response_model=IntentClassifyResponse,
        notes=(
            "학습셋: `exports/intent_trainset.parquet` (split 컬럼으로 train/val 8:2). "
            "라벨 불확실 시 NONE + 낮은 confidence 를 반환하고 예외를 던지지 않는다."
        ),
    ),
    EndpointSpec(
        key="clienteling_reply",
        method="POST",
        path="/clienteling/reply",
        owner="AI2 (클라이언텔링 상담)",
        summary="망설임 유형과 소유 자산을 근거로 상담 문구를 생성한다",
        request_model=ClientelingReplyRequest,
        response_model=ClientelingReplyResponse,
        notes=(
            "RAG 문서: `exports/catalog_rag.jsonl`, "
            "고객 컨텍스트: `exports/customer_context.json`. "
            "**owned_assets 가 비어 있지 않으면 cited_asset_ids 를 반드시 채운다.**"
        ),
    ),
    EndpointSpec(
        key="clienteling_outreach",
        method="POST",
        path="/clienteling/outreach",
        owner="AI2 (클라이언텔링 상담)",
        summary="어드바이저가 먼저 건네는 첫 마디 — 케어 임박 자산 등 계기가 있을 때만",
        request_model=ClientelingOutreachRequest,
        response_model=ClientelingOutreachResponse,
        notes=(
            "계기가 없으면 `message: null` 로 응답한다 — 화면은 아무것도 띄우지 않는다. "
            "AI2 실서버는 계기 없음을 400 으로 주며, 통합 레이어 HTTP 어댑터가 "
            "`message: null` 로 흡수한다(에러 아님)."
        ),
    ),
    EndpointSpec(
        key="assets_list",
        method="GET",
        path="/assets/{customer_id}",
        owner="백엔드 (개체/자산)",
        summary="고객이 소유한 개체 목록과 컨디션을 반환한다",
        request_model=None,
        response_model=CustomerAssetsResponse,
        notes="정렬은 오케스트레이터가 한다. 백엔드는 정렬하지 않아도 된다.",
    ),
    EndpointSpec(
        key="fingerprint_match",
        method="POST",
        path="/fingerprint/match",
        owner="백엔드 (개체 지문)",
        summary="촬영 이미지를 등록 개체와 대조한다",
        request_model=FingerprintMatchRequest,
        response_model=FingerprintMatchResponse,
        notes=(
            "등록 경로 규약: `data/fingerprints/{asset_id}/{angle}_{index}.jpg`. "
            "품질 검증과 경로 등록은 `scripts/register_fingerprint.py` 가 이미 처리한다."
        ),
    ),
    EndpointSpec(
        key="condition_score",
        method="POST",
        path="/condition/score",
        owner="백엔드 (컨디션)",
        summary="개체의 컨디션 점수와 부위별 소견을 반환한다",
        request_model=ConditionScoreRequest,
        response_model=ConditionScoreResponse,
        notes="컨디션 70 이 케어 권장 임계값. next_service_months=0 이면 즉시 권장.",
    ),
    EndpointSpec(
        key="session_advise",
        method="POST",
        path="/session/advise",
        owner="통합/데모 (이 레포)",
        summary="위 모듈을 조합한 최종 상담 응답 — 프론트의 단일 진입점",
        request_model=AdviseRequest,
        response_model=AdviseResponse,
        notes=(
            "인텐트 → 자산 조회 → 컨디션 우선 정렬 → 상담 → 인용 검증. "
            "인용이 비면 `owned_assets_used=false` + 경고 로그."
        ),
    ),
)
