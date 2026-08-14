"""오케스트레이터 — `POST /session/advise` 의 5단계 플로우.

1. 인텐트 분류 (AI1)
2. 고객 소유 자산 조회 (백엔드)
3. 컨디션이 낮거나 서비스 시점이 임박한 자산 우선 정렬 (여기)
4. 상담 생성 (AI2) — 소유 자산과 컨디션을 컨텍스트로 주입
5. **응답 검증** — `cited_asset_ids` 가 비면 경고 로그 + `owned_assets_used=false`

5번이 이 서비스의 존재 이유를 지키는 관측 지점이다. "고객의 물건을 아는 AI" 라고 말하면서
소유 자산을 인용하지 않는 상담이 나가면, 그건 조용히 실패한 것이므로 드러나야 한다.

각 단계는 업스트림 실패를 폴백으로 흡수하고 `degraded` 로 표시한다. 발표 중 빨간 에러 화면이
뜨는 것이 최악의 시나리오이기 때문이다.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.adapters.assets import fallback_assets
from app.adapters.base import AssetPort, ClientelingPort, IntentPort, UpstreamError
from app.adapters.clienteling import fallback_clienteling
from app.adapters.intent import fallback_intent
from app.adapters.registry import get_asset_adapter, get_clienteling_adapter, get_intent_adapter
from app.domain import CARE_THRESHOLD
from app.store import DataStore, get_store
from app.strategies import get_strategy
from contracts.clienteling import ClientelingReplyRequest, ClientelingReplyResponse
from contracts.common import CTA, CustomerTier, HesitationType, OwnedAsset, Product
from contracts.intent import IntentClassifyRequest, IntentClassifyResponse, IntentSignal
from contracts.orchestrator import (
    AdviseRequest,
    AdviseResponse,
    AdviseTraceStep,
    AssetCitation,
    OwnedAssetRanked,
)

logger = logging.getLogger("app.orchestrator")


class ProductNotFound(LookupError):
    """상담 대상 상품이 카탈로그에 없다."""


@dataclass
class StepResult:
    """단계 실행 결과(추적용)."""

    step: str
    adapter: str
    mode: str
    elapsed_ms: float
    degraded: bool
    detail: str

    def to_trace(self) -> AdviseTraceStep:
        return AdviseTraceStep(
            step=self.step,
            adapter=self.adapter,
            mode=self.mode,
            elapsed_ms=round(self.elapsed_ms, 2),
            degraded=self.degraded,
            detail=self.detail[:200],
        )


def rank_assets(assets: list[OwnedAsset], target: Product) -> list[OwnedAssetRanked]:
    """컨디션·케어 시점·카테고리 일치로 인용 우선순위를 매긴다.

    - 컨디션이 낮을수록 높은 점수 (케어 제안 근거가 된다)
    - 케어 시점이 임박하면 가산 (`next_service_months`)
    - 대상 상품과 같은 카테고리면 가산 (사이즈·라스트·소재 이야기가 성립한다)
    """
    ranked: list[OwnedAssetRanked] = []
    for asset in assets:
        wear = (100 - asset.condition_score) / 100.0
        if asset.next_service_months == 0:
            urgency, urgency_note = 1.0, "케어 즉시 권장"
        elif asset.next_service_months <= 3:
            urgency, urgency_note = 0.6, f"케어 {asset.next_service_months}개월 내"
        elif asset.next_service_months <= 6:
            urgency, urgency_note = 0.25, f"케어 {asset.next_service_months}개월 내"
        else:
            urgency, urgency_note = 0.0, "케어 여유"
        same = asset.category is target.category
        priority = round(wear + urgency + (0.5 if same else 0.0), 3)
        reason = f"컨디션 {asset.condition_score}점 / {urgency_note}"
        if same:
            reason += " / 동일 카테고리"
        ranked.append(
            OwnedAssetRanked(
                **asset.model_dump(),
                priority=priority,
                priority_reason=reason,
            )
        )
    ranked.sort(key=lambda a: (-a.priority, a.asset_id))
    return ranked


def _citation_cards(cited_ids: list[str], assets: list[OwnedAsset]) -> list[AssetCitation]:
    by_id = {a.asset_id: a for a in assets}
    cards: list[AssetCitation] = []
    for asset_id in cited_ids:
        asset = by_id.get(asset_id)
        if asset is None:
            continue
        cards.append(
            AssetCitation(
                asset_id=asset.asset_id,
                product_name=asset.product_name,
                condition_score=asset.condition_score,
                next_service_months=asset.next_service_months,
                headline_finding=asset.findings[0].note if asset.findings else None,
            )
        )
    return cards


class Orchestrator:
    """세 모듈을 조합해 최종 상담 응답을 만든다."""

    def __init__(
        self,
        intent: IntentPort | None = None,
        assets: AssetPort | None = None,
        clienteling: ClientelingPort | None = None,
        store: DataStore | None = None,
    ) -> None:
        self.intent = intent or get_intent_adapter()
        self.asset_port = assets or get_asset_adapter()
        self.clienteling = clienteling or get_clienteling_adapter()
        self.store = store or get_store()

    # ── 단계 1: 인텐트 ─────────────────────────────────────────
    def _classify(self, request: AdviseRequest) -> tuple[IntentClassifyResponse, StepResult]:
        started = time.perf_counter()
        if not request.session_events:
            # 계약상 세션 이벤트는 비울 수 있다(일반 제안 모드). AI1 은 최소 1건을 요구하므로
            # 호출하지 않고 NONE 으로 처리한다.
            result = IntentClassifyResponse(
                hesitation_type=HesitationType.NONE,
                confidence=0.3,
                signals=[
                    IntentSignal(
                        name="no_session_events",
                        weight=0.0,
                        evidence="세션 이벤트 없이 요청됨 → 일반 제안 모드",
                    )
                ],
            )
            elapsed = (time.perf_counter() - started) * 1000
            return result, StepResult(
                "intent", "skipped", "local", elapsed, False, "세션 이벤트 없음 → NONE"
            )
        payload = IntentClassifyRequest(
            customer_id=request.customer_id,
            session_events=list(request.session_events),
        )
        adapter_name = type(self.intent).__name__
        mode = self.intent.status.mode
        try:
            result = self.intent.classify(payload)
            degraded, detail = False, f"{result.hesitation_type.value} ({result.confidence:.2f})"
        except (UpstreamError, ValueError) as exc:
            result = fallback_intent(payload)
            degraded, mode = True, "fallback"
            detail = f"업스트림 실패 → 규칙 폴백: {exc}"
            logger.warning("인텐트 분류 폴백: %s", exc)
        elapsed = (time.perf_counter() - started) * 1000
        return result, StepResult("intent", adapter_name, mode, elapsed, degraded, detail)

    # ── 단계 2: 소유 자산 ──────────────────────────────────────
    def _assets(self, request: AdviseRequest) -> tuple[list[OwnedAsset], str, StepResult]:
        started = time.perf_counter()
        adapter_name = type(self.asset_port).__name__
        mode = self.asset_port.status.mode
        try:
            response = self.asset_port.assets(request.customer_id)
            degraded, detail = False, f"{len(response.assets)}개 개체"
        except (UpstreamError, ValueError) as exc:
            response = fallback_assets(request.customer_id, self.store)
            degraded, mode = True, "fallback"
            detail = f"업스트림 실패 → 로컬 산출물: {exc}"
            logger.warning("소유 자산 조회 폴백: %s", exc)
        elapsed = (time.perf_counter() - started) * 1000
        return (
            list(response.assets),
            response.tier.value,
            StepResult("assets", adapter_name, mode, elapsed, degraded, detail),
        )

    # ── 단계 4: 상담 ──────────────────────────────────────────
    def _reply(
        self,
        request: AdviseRequest,
        intent: IntentClassifyResponse,
        target: Product,
        ranked: list[OwnedAssetRanked],
    ) -> tuple[ClientelingReplyResponse, StepResult]:
        started = time.perf_counter()
        payload = ClientelingReplyRequest(
            customer_id=request.customer_id,
            hesitation_type=intent.hesitation_type,
            target_product=target,
            owned_assets=[OwnedAsset.model_validate(a.model_dump()) for a in ranked],
            strategy_id=request.strategy_id,
            history=list(request.history),
        )
        adapter_name = type(self.clienteling).__name__
        mode = self.clienteling.status.mode
        try:
            result = self.clienteling.reply(payload)
            degraded = False
            detail = f"인용 {len(result.cited_asset_ids)}건 / CTA {result.cta.value}"
        except (UpstreamError, ValueError) as exc:
            result = fallback_clienteling(payload)
            degraded, mode = True, "fallback"
            detail = f"업스트림 실패 → 템플릿 폴백: {exc}"
            logger.warning("상담 생성 폴백: %s", exc)
        elapsed = (time.perf_counter() - started) * 1000
        return result, StepResult("clienteling", adapter_name, mode, elapsed, degraded, detail)

    # ── 전체 ─────────────────────────────────────────────────
    def advise(self, request: AdviseRequest) -> AdviseResponse:
        target = self.store.product(request.target_product_id)
        if target is None:
            raise ProductNotFound(f"상품을 찾을 수 없다: {request.target_product_id}")

        intent, intent_step = self._classify(request)
        assets, tier, assets_step = self._assets(request)

        rank_started = time.perf_counter()
        ranked = rank_assets(assets, target)
        rank_elapsed = (time.perf_counter() - rank_started) * 1000
        top_note = (
            f"1순위 {ranked[0].asset_id} ({ranked[0].priority_reason})" if ranked else "개체 없음"
        )
        rank_step = StepResult(
            "rank", "Orchestrator.rank_assets", "local", rank_elapsed, False, top_note
        )

        reply, reply_step = self._reply(request, intent, target, ranked)

        # ── 단계 5: 인용 검증 ──────────────────────────────────
        validate_started = time.perf_counter()
        owned_ids = {a.asset_id for a in assets}
        valid_cited = [cid for cid in reply.cited_asset_ids if cid in owned_ids]
        dropped = [cid for cid in reply.cited_asset_ids if cid not in owned_ids]
        no_assets = not assets
        owned_assets_used = bool(valid_cited)
        strategy = get_strategy(request.strategy_id)

        if dropped:
            logger.warning(
                "상담 응답이 고객 소유가 아닌 개체를 인용했다 (제거): %s (customer=%s)",
                dropped,
                request.customer_id,
            )
        if not owned_assets_used and not no_assets:
            level = logger.warning if strategy.cite_assets else logger.info
            level(
                "소유 자산 인용 없음 — owned_assets_used=false "
                "(customer=%s, strategy=%s, cite_assets=%s, 보유 %d개)",
                request.customer_id,
                strategy.id,
                strategy.cite_assets,
                len(assets),
            )
        validate_detail = (
            f"인용 {len(valid_cited)}건"
            + (f" / 제거 {len(dropped)}건" if dropped else "")
            + (" / 소유 개체 없음" if no_assets else "")
        )
        validate_step = StepResult(
            "validate",
            "Orchestrator.validate",
            "local",
            (time.perf_counter() - validate_started) * 1000,
            False,
            validate_detail,
        )

        steps = [intent_step, assets_step, rank_step, reply_step, validate_step]
        degraded = any(s.degraded for s in steps)
        cta = reply.cta
        if not owned_assets_used and cta is CTA.CARE_BOOKING:
            # 근거 없이 케어를 제안하지 않는다.
            cta = (
                CTA.BOOK_FITTING
                if intent.hesitation_type is HesitationType.SIZE_UNCERTAIN
                else CTA.NONE
            )

        return AdviseResponse(
            request_id=f"adv-{request.customer_id}-{target.product_id}-{strategy.id}",
            customer_id=request.customer_id,
            tier=CustomerTier(tier),
            hesitation_type=intent.hesitation_type,
            confidence=intent.confidence,
            signals=intent.signals,
            message=reply.message,
            cta=cta,
            cited_asset_ids=valid_cited,
            citations=_citation_cards(valid_cited, assets),
            owned_assets_used=owned_assets_used,
            no_assets=no_assets,
            ranked_asset_ids=[a.asset_id for a in ranked],
            strategy_id=strategy.id,
            degraded=degraded,
            reasoning=reply.reasoning,
            trace=[s.to_trace() for s in steps],
        )


def care_due_assets(assets: list[OwnedAsset]) -> list[OwnedAsset]:
    """케어 임계 이하이거나 3개월 내 케어 권장인 개체(대시보드·시나리오용)."""
    return [a for a in assets if a.condition_score <= CARE_THRESHOLD or a.next_service_months <= 3]
