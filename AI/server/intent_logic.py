"""AI1 망설임 분류 — `AI/AI1_intent_classify.ipynb` 5절(계약 구현)을 그대로 옮긴 것.

**로직을 여기서 고치지 않는다.** 이 파일은 노트북 셀 5-1 ~ 5-5 의 승격(promotion)이며,
분류 규칙을 바꾸려면 노트북에서 바꾸고 이 파일에 다시 반영한다(AI1 담당 소유).
검증은 `test_contract.py` — 노트북 셀 5-6(계약 예시 완전 일치)·5-7(라벨 5종)과 동일 케이스.

계약: docs/CONTRACTS.md 의 POST /intent/classify
"""

from typing import Optional

# #### 5-1. 라벨 정의 — 계약과 동일한 5종 고정
HESITATION_TYPES = ["SIZE_UNCERTAIN", "PRICE_HESITANT", "STYLE_DOUBT", "STOCK_CONCERN", "NONE"]

# 라벨 우선순위: 여러 유형의 신호가 동시에 잡히면 이 순서로 하나만 고른다.
PRIORITY = ["STOCK_CONCERN", "SIZE_UNCERTAIN", "PRICE_HESITANT", "STYLE_DOUBT"]


# #### 5-2. 요청 검증
def validate_request(req: dict):
    """IntentClassifyRequest 스펙(customer_id 필수, session_events min_len 1)을 검증.
    형식이 잘못된 요청은 여기서 예외를 던진다. (라벨 자체가 불확실한 것과는 다른 문제)
    """
    if not req.get("customer_id"):
        raise ValueError("customer_id는 필수입니다.")
    events = req.get("session_events")
    if not events or len(events) < 1:
        raise ValueError("session_events는 최소 1건 이상이어야 합니다.")
    return True


# #### 5-3. session_events → 신호(signal) 추출
# docs/CONTRACTS.md 의 SessionEvent / EventType / HesitationType 정의를 그대로 반영했습니다.
#
# meta는 자유 형식(object)이며, 이벤트별 실제 키는 계약 문서 기준:
#   size_guide          -> {'size': '38'}
#   price_filter_change -> {'max_price_krw': 3000000}
#   search               -> {'query': '...'}
#   (extra=allow: 모르는 키는 그대로 보존, 없다고 에러 내지 않음)
#
# EventType enum (전체, 계약 문서 확인 완료): view_product, image_zoom, size_guide,
# price_filter_change, stock_check, shipping_info, care_info, review_read, search,
# back_to_category, wishlist_add, add_to_cart, remove_from_cart, checkout_start, purchase, other
#
# 참고: 상품 category는 SessionEvent.meta에 없고 Product 모델에만 있는 필드라서,
#   "동일 카테고리 저가 상품 반복 조회"를 판단하려면 product_id -> category/price 매핑이 필요합니다.
#   실서비스에서는 카탈로그를 불러와 catalog 인자로 넘기면 되고,
#   catalog가 없으면(예: 노트북의 단독 테스트) 이 신호는 건너뜁니다.

STOCK_EVENT_NAMES = ("stock_check", "shipping_info")
CHECKOUT_EVENT_NAMES = ("checkout_start", "purchase")


def extract_signals(session_events, catalog: Optional[dict] = None):
    """세션 이벤트 시퀀스에서 망설임 유형별 근거 신호를 뽑는다.
    catalog: {product_id: {"category": str, "price_krw": int}} — 있으면 PRICE_HESITANT의
             '동일 카테고리 저가 상품 반복 조회' 판단에 사용. 없으면 해당 신호는 건너뜀.

    signal: {name, weight, evidence, hesitation_type}
    hesitation_type이 None인 신호는 특정 유형을 가리키지 않는 보조/반대 신호로,
    weight가 음수면 해당 라벨(또는 전반적 망설임)을 반박하는 근거다.
    """
    signals = []
    catalog = catalog or {}

    view_events = [e for e in session_events if e.get("event_type") == "view_product"]
    unique_product_set = {e.get("product_id") for e in view_events if e.get("product_id")}

    # ---- SIZE_UNCERTAIN: size_guide 반복 조회, 동일 상품 사이즈 왕복 ----
    size_guide_events = [e for e in session_events if e.get("event_type") == "size_guide"]
    if len(size_guide_events) >= 2:
        sizes = [e.get("meta", {}).get("size") for e in size_guide_events if e.get("meta", {}).get("size")]
        weight = round(min(0.75, 0.5 + 0.12 * (len(size_guide_events) - 1)), 2)
        evidence = f"size_guide {len(size_guide_events)}회 조회"
        if sizes:
            evidence += f" ({', '.join(sizes)})"
        signals.append({"name": "size_guide_repeat", "weight": weight, "evidence": evidence,
                         "hesitation_type": "SIZE_UNCERTAIN"})

    # ---- PRICE_HESITANT: 가격 필터 하향 ----
    price_filter_events = [e for e in session_events if e.get("event_type") == "price_filter_change"]
    price_filter_events = [e for e in price_filter_events if e.get("meta", {}).get("max_price_krw") is not None]
    if len(price_filter_events) >= 2:
        prices = [e["meta"]["max_price_krw"] for e in price_filter_events]
        lowered = all(prices[i] >= prices[i + 1] for i in range(len(prices) - 1)) and prices[0] > prices[-1]
        if lowered:
            weight = round(min(0.75, 0.5 + 0.1 * (len(price_filter_events) - 1)), 2)
            signals.append({"name": "price_filter_lowered", "weight": weight,
                             "evidence": f"가격 필터 하향 {prices[0]:,}원 → {prices[-1]:,}원",
                             "hesitation_type": "PRICE_HESITANT"})

    # ---- PRICE_HESITANT: 동일 카테고리 저가 상품 반복 조회 (catalog 있을 때만) ----
    if catalog and view_events:
        cat_price = [(catalog.get(e.get("product_id"), {}).get("category"),
                      catalog.get(e.get("product_id"), {}).get("price_krw"))
                     for e in view_events if e.get("product_id") in catalog]
        categories = {c for c, _ in cat_price if c}
        prices_seen = [p for _, p in cat_price if p is not None]
        if len(categories) == 1 and len(cat_price) >= 3 and prices_seen:
            avg_price = sum(prices_seen) / len(prices_seen)
            # 카탈로그 전체 평균 대비 낮은 가격대 상품 위주인지까지는 알 수 없어
            # 같은 카테고리를 3회 이상 반복 조회했다는 사실 자체를 근거로 삼는다 (보수적 버전)
            weight = round(min(0.6, 0.35 + 0.08 * (len(cat_price) - 3)), 2)
            signals.append({"name": "same_category_repeat", "weight": weight,
                             "evidence": f"동일 카테고리('{next(iter(categories))}') 상품 {len(cat_price)}회 반복 조회",
                             "hesitation_type": "PRICE_HESITANT"})

    # ---- STYLE_DOUBT: 여러 상품 왕복, 장시간 체류, 결정 없음 ----
    has_cart = any(e.get("event_type") == "add_to_cart" for e in session_events)
    has_checkout = any(e.get("event_type") in CHECKOUT_EVENT_NAMES for e in session_events)
    total_dwell = sum(e.get("dwell_seconds", 0) or 0 for e in view_events)
    seq = [e.get("product_id") for e in view_events]
    back_and_forth = len(unique_product_set) >= 2 and any(
        seq[i] != seq[i + 1] and seq[i] in seq[i + 2:] for i in range(len(seq) - 1)
    )
    back_to_category_count = sum(1 for e in session_events if e.get("event_type") == "back_to_category")

    if (len(unique_product_set) >= 3 or back_to_category_count >= 2) and not has_cart and not has_checkout:
        weight = round(min(0.75, 0.4
                            + 0.06 * max(0, len(unique_product_set) - 3)
                            + (0.1 if back_and_forth else 0)
                            + (0.1 if total_dwell >= 120 else 0)
                            + (0.05 * back_to_category_count)), 2)
        evidence = (f"서로 다른 상품 {len(unique_product_set)}건 조회, "
                    f"카테고리 재진입 {back_to_category_count}회, "
                    f"총 체류 {total_dwell:.0f}초, 장바구니/결제 없음")
        signals.append({"name": "wide_browse_no_decision", "weight": weight, "evidence": evidence,
                         "hesitation_type": "STYLE_DOUBT"})

    # ---- STOCK_CONCERN: 재고·배송 페이지 조회 (stock_check, shipping_info) ----
    stock_events = [e for e in session_events if e.get("event_type") in STOCK_EVENT_NAMES]
    if len(stock_events) >= 1:
        weight = round(min(0.75, 0.55 + 0.1 * (len(stock_events) - 1)), 2)
        types_seen = sorted({e.get("event_type") for e in stock_events})
        signals.append({"name": "stock_delivery_check", "weight": weight,
                         "evidence": f"재고/배송 페이지 조회 {len(stock_events)}회 ({', '.join(types_seen)})",
                         "hesitation_type": "STOCK_CONCERN"})

    # ---- 보조/반대 신호 (특정 라벨에 속하지 않음, weight 음수 가능) ----
    if has_cart and not has_checkout:
        signals.append({"name": "cart_without_checkout", "weight": 0.2,
                         "evidence": "장바구니 담기 후 결제 진입 없음", "hesitation_type": None})

    if has_checkout:
        # checkout_start/purchase까지 갔다면 "망설임이 아니다"를 뒷받침하는 반대 근거 -> 음수 weight
        signals.append({"name": "checkout_completed", "weight": -0.3,
                         "evidence": "checkout_start/purchase 이벤트 존재", "hesitation_type": None})

    return signals


# #### 5-4. 신호 → 최종 hesitation_type / confidence
def classify_hesitation_type(session_events, catalog: Optional[dict] = None):
    """우선순위에 따라 유형을 하나 고르고, 관련 신호 weight 합을 confidence로 쓴다.
    - weight는 음수일 수 있어서(반대 근거) 최종 confidence는 0~1로 clip한다.
    - 특정 유형 신호가 하나도 안 잡히면 NONE (구 QUICK_EXIT / GENERAL_BROWSE 흡수) + 낮은 confidence
    - 라벨이 불확실한 상황이어도 예외를 던지지 않는다 (계약 비고 사항 준수)
    """
    signals = extract_signals(session_events, catalog=catalog)
    typed_signals = {s["hesitation_type"]: s for s in signals if s["hesitation_type"]}

    chosen_type = "NONE"
    for t in PRIORITY:
        if t in typed_signals:
            chosen_type = t
            break

    generic = [s for s in signals if s["hesitation_type"] is None]

    if chosen_type == "NONE":
        generic_weight = sum(s["weight"] for s in generic)
        confidence = round(max(0.05, min(0.3, generic_weight)), 2) if generic_weight > 0 else 0.1
        out_signals = [{"name": s["name"], "weight": s["weight"], "evidence": s["evidence"]} for s in generic]
        return {"hesitation_type": "NONE", "confidence": confidence, "signals": out_signals}

    # 선택된 유형의 신호 + 보조/반대 신호(hesitation_type=None)를 함께 근거로 포함
    relevant = [s for s in signals if s["hesitation_type"] == chosen_type or s["hesitation_type"] is None]
    confidence = round(max(0.0, min(1.0, sum(s["weight"] for s in relevant))), 2)
    out_signals = [{"name": s["name"], "weight": s["weight"], "evidence": s["evidence"]} for s in relevant]
    return {"hesitation_type": chosen_type, "confidence": confidence, "signals": out_signals}


# #### 5-5. POST /intent/classify 엔드포인트 함수
def predict_intent(request: dict, catalog: Optional[dict] = None) -> dict:
    """IntentClassifyRequest -> IntentClassifyResponse
    catalog는 계약 스키마 밖의 선택적 인자다 (product_id -> category/price 매핑, 있으면 더 정확한 분류).
    """
    validate_request(request)
    result = classify_hesitation_type(request["session_events"], catalog=catalog)
    assert result["hesitation_type"] in HESITATION_TYPES, "계약에 없는 라벨이 나왔습니다."
    return result
