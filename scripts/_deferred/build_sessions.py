"""세션 이벤트 구축 — 클릭스트림 → 이탈 세션 60개 + 망설임 라벨.

원본(`ecommerce_clickstream_transactions.csv`)에서 살아남는 정보와 합성해야 하는 정보를
분명히 나눈다. 심사위원이 "이 데이터 진짜냐"고 물을 때 답할 근거가 여기와
`docs/DATA_PROVENANCE.md` 에 남는다.

원본에서 그대로 쓰는 것
    - 세션 구성: `(UserID, SessionID)` 조합. **`SessionID` 단독은 1~10 버킷일 뿐**이고
      버킷당 이벤트가 7,481개라 세션이 될 수 없다.
    - 이벤트 종류/개수/순서: page_view, product_view, click, add_to_cart, purchase, login, logout
    - 이탈 판정: add_to_cart 있고 purchase 없음
    - 상품 참조 횟수(같은 prod_xxxx 반복 조회 횟수), 세션당 상품 다양성

합성해야 하는 것 (원본에 없음)
    - 판별 이벤트: size_guide / price_filter_change / stock_check / shipping_info /
      back_to_category / image_zoom  ← 원본 어휘가 7종뿐이라 불가피
    - 시간축: 원본은 한 세션의 타임스탬프가 수개월에 걸쳐 흩어져 있어 세션 시간축으로 쓸 수 없다.
      순서만 살리고 시각/체류시간은 규칙 합성한다.
    - 우리 고객·상품과의 연결(원본 UserID/ProductID → CU-xxxx / LX-xxxx 결정적 매핑)

라벨은 **합성된 최종 이벤트 시퀀스에 `app.intent_rules` 규칙을 적용해 도출**한다.
목표 라벨을 먼저 정하고 근거를 만드는 방식이 아니다(그러면 학습셋이 완전히 순환한다).
그래도 판별 이벤트 자체가 원본 통계에서 파생 합성된 것이므로, 이 학습셋은 "사람의 실제 라벨"이
아니라 "규칙의 근사"라는 한계를 갖는다. DATA_PROVENANCE.md 에 그대로 적어 둔다.

    python -m scripts.build_sessions
    python -m scripts.build_sessions --force
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import polars as pl

from app.config import PROCESSED_DIR, get_settings
from app.domain import stable_hash
from app.intent_rules import classify, rule_name
from contracts.common import EventType, HesitationType, Product, ProductCategory, SessionEvent
from scripts.common import (
    CATALOG_PATH,
    CLICKSTREAM_CSV,
    CUSTOMERS_PATH,
    REFERENCE_NOW,
    banner,
    decide_source,
    read_json,
    record_provenance,
    session_id,
    write_json,
)
from scripts.synth_fallback import synth_clickstream

N_SESSIONS = 60

#: 사이즈 선택이 존재하는 카테고리. 여기가 아니면 size_guide 이벤트를 만들지 않는다.
SIZED_CATEGORIES = {
    ProductCategory.SHOES,
    ProductCategory.BELT,
    ProductCategory.OUTERWEAR,
    ProductCategory.BAG,
}

#: 이벤트별 체류시간 범위(초). 합성 값이며 원본에는 체류시간 컬럼이 없다.
DWELL_RANGES: dict[EventType, tuple[int, int]] = {
    EventType.VIEW_PRODUCT: (25, 130),
    EventType.IMAGE_ZOOM: (10, 45),
    EventType.SIZE_GUIDE: (45, 150),
    EventType.PRICE_FILTER_CHANGE: (8, 25),
    EventType.STOCK_CHECK: (20, 70),
    EventType.SHIPPING_INFO: (25, 80),
    EventType.CARE_INFO: (30, 90),
    EventType.REVIEW_READ: (40, 160),
    EventType.SEARCH: (10, 40),
    EventType.BACK_TO_CATEGORY: (12, 60),
    EventType.WISHLIST_ADD: (5, 15),
    EventType.ADD_TO_CART: (4, 14),
    EventType.REMOVE_FROM_CART: (4, 12),
    EventType.CHECKOUT_START: (15, 60),
    EventType.PURCHASE: (20, 90),
    EventType.OTHER: (5, 30),
}


@dataclass
class RawSession:
    """원본 세션 하나. (UserID, SessionID) 조합 단위."""

    user_id: str
    bucket: str
    kinds: Counter[str] = field(default_factory=Counter)
    order: list[str] = field(default_factory=list)
    product_refs: Counter[str] = field(default_factory=Counter)
    post_cart_events: int = 0
    amount: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.user_id}:{self.bucket}"

    @property
    def abandoned(self) -> bool:
        return self.kinds["add_to_cart"] > 0 and self.kinds["purchase"] == 0

    @property
    def distinct_products(self) -> int:
        return len(self.product_refs)

    @property
    def repeat_max(self) -> int:
        return max(self.product_refs.values()) if self.product_refs else 0


def load_raw_sessions() -> tuple[list[RawSession], str, dict[str, Any]]:
    """클릭스트림을 (UserID, SessionID) 단위 세션으로 묶는다."""
    decision = decide_source("sessions", CLICKSTREAM_CSV)
    print(f"  소스: {decision.label} — {decision.reason}")
    if decision.used_external:
        frame = pl.read_csv(CLICKSTREAM_CSV, ignore_errors=True, truncate_ragged_lines=True)
        rows = frame.to_dicts()
    else:
        rows = synth_clickstream(seed=get_settings().seed)

    sessions: dict[str, RawSession] = {}
    for row in rows:
        user_id = str(row.get("UserID") or "")
        bucket = str(row.get("SessionID") or "")
        if not user_id or not bucket:
            continue
        key = f"{user_id}:{bucket}"
        sess = sessions.get(key)
        if sess is None:
            sess = RawSession(user_id=user_id, bucket=bucket)
            sessions[key] = sess
        event_type = str(row.get("EventType") or "other")
        sess.kinds[event_type] += 1
        sess.order.append(event_type)
        product = str(row.get("ProductID") or "").strip()
        if product:
            sess.product_refs[product] += 1
        if "add_to_cart" in sess.order and event_type in {"page_view", "click", "product_view"}:
            sess.post_cart_events += 1
        with suppress(TypeError, ValueError):
            sess.amount += float(row.get("Amount") or 0)

    ordered = sorted(sessions.values(), key=lambda s: s.key)
    meta = {
        "source": decision.label,
        "reason": decision.reason,
        "raw_rows": len(rows),
        "raw_sessions": len(ordered),
        "session_unit": "(UserID, SessionID)",
    }
    print(f"  원본 {len(rows):,}행 → 세션 {len(ordered):,}개")
    return ordered, decision.label, meta


def select_sessions(sessions: list[RawSession]) -> list[RawSession]:
    """이탈 세션(add_to_cart 있고 purchase 없음)만 골라 60개를 결정적으로 뽑는다."""
    abandoned = [s for s in sessions if s.abandoned]
    print(f"  이탈 세션: {len(abandoned):,}개 / 전체 {len(sessions):,}개")
    if len(abandoned) < N_SESSIONS:
        print(f"  ! 이탈 세션이 {len(abandoned)}개뿐 → 구매 완료 세션을 섞어 보충한다")
        extra = [s for s in sessions if not s.abandoned]
        extra.sort(key=lambda s: stable_hash("extra", s.key))
        abandoned = abandoned + extra[: N_SESSIONS - len(abandoned)]
    abandoned.sort(key=lambda s: stable_hash("session", s.key))
    return abandoned[:N_SESSIONS]


def dwell_for(event_type: EventType, salt: str) -> float:
    low, high = DWELL_RANGES.get(event_type, (10, 60))
    span = max(1, high - low)
    return float(low + stable_hash("dwell", event_type.value, salt) % span)


@dataclass
class SessionPlan:
    """세션 하나의 합성 계획."""

    profile: str
    target: Product
    others: list[Product]
    cheaper: Product | None
    scores: dict[str, float]


def choose_profile(
    raw: RawSession,
    target: Product,
    catalog: list[Product],
    avg_owned_price: float,
) -> SessionPlan:
    """원본 통계 + 매핑된 상품/고객 맥락에서 행동 프로파일을 결정적으로 고른다.

    라벨을 직접 고르는 것이 아니라 '어떤 판별 이벤트가 생겼을 만한 세션인가'를 고른다.
    라벨은 그 뒤 규칙 엔진이 이벤트에서 도출한다.
    """
    same_category = [p for p in catalog if p.category is target.category and p != target]
    same_category.sort(key=lambda p: p.price_krw)
    cheaper = next((p for p in same_category if p.price_krw < target.price_krw), None)
    others = [p for p in same_category if p.product_id != target.product_id][:4]

    price_ratio = target.price_krw / max(1.0, avg_owned_price)
    sized = target.category in SIZED_CATEGORIES
    # 가중치는 60개 세션의 라벨 분포가 한쪽으로 쏠리지 않도록 그리드로 보정한 값이다
    # (AI1 학습셋 균형 목적). 프로파일은 여전히 원본 특성의 함수이며 목표 라벨을 먼저 정하지 않는다.
    # 원본의 repeat_max 는 전 세션 1(같은 상품 반복 조회가 없음)이라 신호로 쓰지 않는다.
    scores = {
        # 사이즈 체계가 있는 상품 + 소수 상품에 집중한 세션 → 사이즈 고민
        "size": (0.7 if sized else 0.0) + 0.3 * max(0, 3 - raw.distinct_products),
        # 고객 보유 자산 평균가 대비 비싼 대상 + 클릭 탐색 많음 → 가격 부담
        "price": 1.4 * max(0.0, price_ratio - 1.15) + 0.15 * raw.kinds["click"],
        # 서로 다른 상품을 많이 본 세션 → 취향 확신 부족
        "style": 0.7 * max(0, raw.distinct_products - 2),
        # 장바구니 이후에도 계속 탐색 → 재고/배송 확인
        "stock": 0.4 * raw.post_cart_events,
        "none": 0.8,
    }
    # 동점 방지용 결정적 미세 가중치.
    for name in scores:
        scores[name] += (stable_hash("tie", raw.key, name) % 100) / 1000.0
    profile = max(scores, key=lambda k: scores[k])
    return SessionPlan(
        profile=profile, target=target, others=others, cheaper=cheaper, scores=scores
    )


def synthesize_events(raw: RawSession, plan: SessionPlan) -> list[SessionEvent]:
    """원본 이벤트 순서를 뼈대로 두고 판별 이벤트를 규칙 합성해 끼운다."""
    start = REFERENCE_NOW - timedelta(
        days=1 + stable_hash("startday", raw.key) % 30,
        minutes=stable_hash("startmin", raw.key) % 600,
    )
    cursor = start
    events: list[SessionEvent] = []
    others = plan.others or [plan.target]

    def add(
        event_type: EventType,
        product_id: str | None,
        meta: dict[str, Any],
        synthetic: bool,
    ) -> None:
        nonlocal cursor
        salt = f"{raw.key}:{len(events)}"
        gap = 10 + stable_hash("gap", salt) % 170
        cursor = cursor + timedelta(seconds=gap)
        events.append(
            SessionEvent(
                event_type=event_type,
                product_id=product_id,
                timestamp=cursor,
                dwell_seconds=dwell_for(event_type, salt),
                meta={**meta, "synthetic": synthetic},
            )
        )

    # 1) 원본 이벤트 뼈대 (login/logout 은 상담과 무관하므로 버린다)
    view_idx = 0
    for kind in raw.order:
        if kind == "product_view":
            product = plan.target if view_idx % 2 == 0 else others[view_idx % len(others)]
            add(EventType.VIEW_PRODUCT, product.product_id, {"from_raw": "product_view"}, False)
            view_idx += 1
        elif kind == "page_view":
            add(EventType.BACK_TO_CATEGORY, None, {"from_raw": "page_view"}, False)
        elif kind == "click":
            add(EventType.IMAGE_ZOOM, plan.target.product_id, {"from_raw": "click"}, False)
        elif kind == "add_to_cart":
            add(EventType.ADD_TO_CART, plan.target.product_id, {"from_raw": "add_to_cart"}, False)
        elif kind == "purchase":
            add(EventType.PURCHASE, plan.target.product_id, {"from_raw": "purchase"}, False)

    # 2) 프로파일별 판별 이벤트 합성
    if plan.profile == "size":
        sizes = plan.target.available_sizes or ["38", "38.5"]
        picked = [sizes[0], sizes[min(1, len(sizes) - 1)]]
        repeats = 2 + stable_hash("sizerep", raw.key) % 2
        for i in range(repeats):
            add(
                EventType.SIZE_GUIDE,
                plan.target.product_id,
                {"size": picked[i % len(picked)], "size_system": plan.target.size_system},
                True,
            )
    elif plan.profile == "price":
        cap = int(plan.target.price_krw * 0.7 // 100_000 * 100_000)
        add(EventType.PRICE_FILTER_CHANGE, None, {"max_price_krw": cap}, True)
        if plan.cheaper is not None:
            for _ in range(1 + stable_hash("cheap", raw.key) % 2):
                add(
                    EventType.VIEW_PRODUCT,
                    plan.cheaper.product_id,
                    {
                        "cheaper_alternative": True,
                        "price_krw": plan.cheaper.price_krw,
                        "reference_price_krw": plan.target.price_krw,
                    },
                    True,
                )
    elif plan.profile == "style":
        for product in others[:3]:
            add(EventType.VIEW_PRODUCT, product.product_id, {"comparison": True}, True)
            add(EventType.BACK_TO_CATEGORY, None, {"comparison": True}, True)
    elif plan.profile == "stock":
        add(
            EventType.STOCK_CHECK,
            plan.target.product_id,
            {"available_sizes": plan.target.available_sizes},
            True,
        )
        if stable_hash("ship", raw.key) % 2 == 0:
            add(EventType.SHIPPING_INFO, plan.target.product_id, {"eta_days": 5}, True)

    events.sort(key=lambda e: e.timestamp)
    return events


def main() -> int:
    ap = argparse.ArgumentParser(description="이탈 세션 60개 + 망설임 라벨 구축")
    ap.add_argument("--force", action="store_true", help="기존 sessions.json 덮어쓰기")
    args = ap.parse_args()

    banner("세션 이벤트 구축")
    from scripts.common import SESSIONS_PATH

    if SESSIONS_PATH.exists() and not args.force:
        print(f"  이미 존재: {SESSIONS_PATH.name} → 재생성하려면 --force")
        return 0
    for path, hint in ((CATALOG_PATH, "build_catalog"), (CUSTOMERS_PATH, "build_customers")):
        if not path.exists():
            print(f"  ! {path.name} 이 없다. 먼저 `python -m scripts.{hint}` 를 실행하라.")
            return 1

    catalog = [Product.model_validate(item) for item in read_json(CATALOG_PATH)["items"]]
    customers = read_json(CUSTOMERS_PATH)["customers"]
    catalog_by_id = {p.product_id: p for p in catalog}
    avg_price_by_customer: dict[str, float] = {}
    for cust in customers:
        prices = [
            catalog_by_id[a["product_id"]].price_krw
            for a in cust["assets"]
            if a["product_id"] in catalog_by_id
        ]
        avg_price_by_customer[cust["customer_id"]] = (
            sum(prices) / len(prices) if prices else 2_500_000.0
        )

    raw_sessions, source_label, meta = load_raw_sessions()
    chosen = select_sessions(raw_sessions)

    records: list[dict[str, Any]] = []
    label_counts: Counter[str] = Counter()
    profile_counts: Counter[str] = Counter()

    for idx, raw in enumerate(chosen, start=1):
        cust = customers[stable_hash("cust", raw.key) % len(customers)]
        # 원본에서 가장 많이 참조된 상품을 상담 대상으로 매핑한다.
        top_raw_product = raw.product_refs.most_common(1)[0][0] if raw.product_refs else raw.key
        target = catalog[stable_hash("prod", top_raw_product) % len(catalog)]
        plan = choose_profile(raw, target, catalog, avg_price_by_customer[cust["customer_id"]])
        events = synthesize_events(raw, plan)
        result = classify(events)

        label_counts[result.hesitation_type.value] += 1
        profile_counts[plan.profile] += 1
        records.append(
            {
                "session_id": session_id(idx),
                "customer_id": cust["customer_id"],
                "customer_tier": cust["tier"],
                "target_product_id": plan.target.product_id,
                "target_product_name": plan.target.name,
                "abandoned": raw.abandoned,
                "profile": plan.profile,
                "profile_scores": {k: round(v, 3) for k, v in plan.scores.items()},
                "hesitation_label": result.hesitation_type.value,
                "label_rule": rule_name(result.hesitation_type),
                "label_confidence": result.confidence,
                "signals": [s.model_dump(mode="json") for s in result.signals],
                "raw": {
                    "user_id": raw.user_id,
                    "session_bucket": raw.bucket,
                    "event_count": len(raw.order),
                    "kinds": dict(raw.kinds),
                    "distinct_products": raw.distinct_products,
                    "repeat_max": raw.repeat_max,
                    "post_cart_events": raw.post_cart_events,
                },
                "events": [e.model_dump(mode="json") for e in events],
                "synthetic_event_count": sum(1 for e in events if e.meta.get("synthetic") is True),
            }
        )

    payload = {
        "generated_with": {
            "source": source_label,
            "reference_now": REFERENCE_NOW.isoformat(),
            "seed": get_settings().seed,
            "session_unit": "(UserID, SessionID)",
            "label_engine": "app.intent_rules.classify",
            "label_counts": dict(label_counts),
            "profile_counts": dict(profile_counts),
        },
        "sessions": records,
    }
    from scripts.common import SESSIONS_PATH as OUT

    write_json(OUT, payload)
    record_provenance(
        "sessions",
        {
            **meta,
            "selected_sessions": len(records),
            "label_counts": dict(label_counts),
            "profile_counts": dict(profile_counts),
            "synthetic_events": sum(r["synthetic_event_count"] for r in records),
            "total_events": sum(len(r["events"]) for r in records),
        },
    )
    print(f"  저장: {OUT.relative_to(PROCESSED_DIR.parent.parent)} ({len(records)}개 세션)")
    print(f"  라벨 분포: {dict(label_counts)}")
    print(f"  프로파일 분포: {dict(profile_counts)}")
    missing = [t.value for t in HesitationType if t.value not in label_counts]
    if missing:
        print(f"  ! 라벨 누락: {missing} — AI1 학습셋이 불균형해진다. 임계값 보정을 검토하라")
    return 0


if __name__ == "__main__":
    sys.exit(main())
