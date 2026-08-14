"""망설임 유형 휴리스틱 — 세션 이벤트 → 라벨 + 근거.

이 규칙 엔진은 **두 곳에서 같이 쓰인다.**
1. `scripts/build_sessions.py` — AI1 학습셋의 라벨을 만든다.
2. `app/adapters/intent.py` 의 `MockIntentAdapter` — 런타임 목 응답을 만든다.

같은 규칙을 쓰기 때문에 목 응답이 하드코딩 더미가 아니고, AI1 실구현이 들어오면
"규칙 대비 얼마나 나아졌는가"를 같은 기준으로 비교할 수 있다.

규칙 요약 (docs/DATA_PROVENANCE.md 와 동일)
    SIZE_UNCERTAIN  : size_guide 2회 이상 (또는 서로 다른 사이즈 조회)
    PRICE_HESITANT  : 가격 필터 변경, 또는 동일 카테고리 저가 상품 반복 조회
    STYLE_DOUBT     : 서로 다른 상품 4개 이상 왕복 + 총 체류 240초 이상, 결정 없음
    STOCK_CONCERN   : 재고/배송 페이지 조회
    NONE            : 위 신호 없음

`add_to_cart` 후 결제 진입이 없으면 이탈 신호로 보고 최상위 후보에 가중치를 더한다.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from contracts.common import EventType, HesitationType, SessionEvent
from contracts.intent import IntentClassifyResponse, IntentSignal

STYLE_DISTINCT_THRESHOLD = 4
STYLE_DWELL_THRESHOLD = 240.0


def _dwell_total(events: Sequence[SessionEvent]) -> float:
    return sum(e.dwell_seconds for e in events)


def classify(events: Sequence[SessionEvent]) -> IntentClassifyResponse:
    """이벤트 시퀀스에서 망설임 유형을 규칙으로 도출한다. 항상 응답을 만든다(예외 없음)."""
    if not events:
        return IntentClassifyResponse(
            hesitation_type=HesitationType.NONE,
            confidence=0.3,
            signals=[IntentSignal(name="no_events", weight=0.0, evidence="세션 이벤트가 없음")],
        )

    ordered = sorted(events, key=lambda e: e.timestamp)
    kinds = Counter(e.event_type for e in ordered)
    products = [e.product_id for e in ordered if e.product_id]
    distinct_products = len(set(products))
    dwell = _dwell_total(ordered)

    scores: dict[HesitationType, float] = dict.fromkeys(HesitationType, 0.0)
    signals: list[IntentSignal] = []

    # ── SIZE_UNCERTAIN ──────────────────────────────────────
    size_events = [e for e in ordered if e.event_type is EventType.SIZE_GUIDE]
    if size_events:
        sizes = [str(e.meta.get("size")) for e in size_events if e.meta.get("size")]
        distinct_sizes = len(set(sizes))
        weight = 0.0
        if len(size_events) >= 2:
            weight += 0.6 + 0.05 * min(4, len(size_events) - 2)
        else:
            weight += 0.25
        if distinct_sizes >= 2:
            weight += 0.15
        scores[HesitationType.SIZE_UNCERTAIN] += weight
        detail = f"({', '.join(sizes)})" if sizes else ""
        signals.append(
            IntentSignal(
                name="size_guide_repeat",
                weight=round(weight, 3),
                evidence=f"size_guide {len(size_events)}회 조회 {detail}".strip(),
            )
        )

    # ── PRICE_HESITANT ──────────────────────────────────────
    filter_changes = kinds[EventType.PRICE_FILTER_CHANGE]
    cheaper_views = sum(1 for e in ordered if e.meta.get("cheaper_alternative") is True)
    if filter_changes or cheaper_views:
        weight = 0.5 * min(1, filter_changes) + 0.12 * min(3, cheaper_views)
        scores[HesitationType.PRICE_HESITANT] += weight
        parts: list[str] = []
        if filter_changes:
            caps = [
                str(e.meta.get("max_price_krw"))
                for e in ordered
                if e.event_type is EventType.PRICE_FILTER_CHANGE and e.meta.get("max_price_krw")
            ]
            cap_note = f" (상한 {caps[-1]}원)" if caps else ""
            parts.append(f"가격 필터 변경 {filter_changes}회{cap_note}")
        if cheaper_views:
            parts.append(f"동일 카테고리 저가 상품 {cheaper_views}회 조회")
        signals.append(
            IntentSignal(
                name="price_sensitivity", weight=round(weight, 3), evidence=", ".join(parts)
            )
        )

    # ── STYLE_DOUBT ─────────────────────────────────────────
    revisits = kinds[EventType.BACK_TO_CATEGORY]
    if distinct_products >= STYLE_DISTINCT_THRESHOLD and dwell >= STYLE_DWELL_THRESHOLD:
        weight = 0.5 + 0.1 * min(3, distinct_products - STYLE_DISTINCT_THRESHOLD)
        if revisits >= 2:
            weight += 0.15
        scores[HesitationType.STYLE_DOUBT] += weight
        signals.append(
            IntentSignal(
                name="wide_browsing",
                weight=round(weight, 3),
                evidence=(
                    f"서로 다른 상품 {distinct_products}개 왕복, 총 체류 {dwell:.0f}초, "
                    f"카테고리 복귀 {revisits}회"
                ),
            )
        )

    # ── STOCK_CONCERN ───────────────────────────────────────
    stock_events = kinds[EventType.STOCK_CHECK]
    shipping_events = kinds[EventType.SHIPPING_INFO]
    if stock_events or shipping_events:
        weight = 0.55 * min(1, stock_events + shipping_events)
        if stock_events and shipping_events:
            weight += 0.15
        scores[HesitationType.STOCK_CONCERN] += weight
        signals.append(
            IntentSignal(
                name="availability_check",
                weight=round(weight, 3),
                evidence=f"재고 조회 {stock_events}회, 배송 정보 {shipping_events}회",
            )
        )

    # ── 이탈 신호(장바구니 후 결제 없음) ────────────────────────
    abandoned = kinds[EventType.ADD_TO_CART] > 0 and (
        kinds[EventType.CHECKOUT_START] + kinds[EventType.PURCHASE] == 0
    )
    top = max(scores, key=lambda k: scores[k])
    if abandoned and scores[top] > 0:
        scores[top] += 0.2
        signals.append(
            IntentSignal(
                name="cart_without_checkout",
                weight=0.2,
                evidence="장바구니 담기 후 결제 진입 없음",
            )
        )

    best = max(scores, key=lambda k: scores[k])
    if scores[best] <= 0.0:
        return IntentClassifyResponse(
            hesitation_type=HesitationType.NONE,
            confidence=0.45 if abandoned else 0.6,
            signals=signals
            or [
                IntentSignal(
                    name="no_hesitation_signal",
                    weight=0.0,
                    evidence=f"판별 이벤트 없음 (이벤트 {len(ordered)}건, 체류 {dwell:.0f}초)",
                )
            ],
        )

    confidence = min(0.95, 0.35 + scores[best])
    signals.sort(key=lambda s: -s.weight)
    return IntentClassifyResponse(
        hesitation_type=best, confidence=round(confidence, 3), signals=signals
    )


def rule_name(label: HesitationType) -> str:
    """라벨을 만든 규칙의 이름(문서·학습셋 기록용)."""
    return {
        HesitationType.SIZE_UNCERTAIN: "size_guide_repeat>=2",
        HesitationType.PRICE_HESITANT: "price_filter_change|cheaper_alternative_views",
        HesitationType.STYLE_DOUBT: "distinct_products>=4 & dwell>=240s",
        HesitationType.STOCK_CONCERN: "stock_check|shipping_info",
        HesitationType.NONE: "no_discriminating_event",
    }[label]
