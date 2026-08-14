"""상담 문구 생성 규칙 — LLM 이 없을 때의 결정적 폴백이자 LLM 프롬프트의 기준선.

`app/intent_rules.py` 와 같은 역할 분담이다. 목 어댑터가 하드코딩 더미를 뱉지 않게,
**전략 × 망설임 유형 × 실제 소유 자산**으로 문장을 조립한다. 데모 화면에 그대로 뜨는 문장이므로
어휘를 신경 써서 만들었다.

전략별 차이가 실험의 측정 대상이다.
    S1 정보 제공형   : 소유 자산을 인용하지 않는다(스펙·재고 사실만)
    S2 소유 자산 연계형: 구매 연도 + 컨디션 점수 + 부위 소견을 인용한다
    S3 희소성 강조형  : 재고 희소성·타이밍을 말한다(자산 인용 없음)

세 전략이 모두 자산을 인용하면 "자산 연계가 효과 있는가"를 측정할 수 없다. 그래서 인용 정책을
전략 정의(`data/strategies.yaml`)에 두고 여기서는 그대로 따른다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import REFERENCE_NOW
from app.domain import CARE_THRESHOLD, years_between
from app.strategies import Strategy
from contracts.clienteling import ClientelingReplyRequest, ClientelingReplyResponse
from contracts.common import CTA, HesitationType, OwnedAsset, Product, ProductCategory

#: 카테고리별 착용/사용 동사. 가방에 "신어 보고" 라고 쓰면 그 자리에서 신뢰를 잃는다.
TRY_VERB: dict[ProductCategory, str] = {
    ProductCategory.SHOES: "신어 보고",
    ProductCategory.BAG: "직접 들어 보고",
    ProductCategory.WATCH: "착용해 보고",
    ProductCategory.BELT: "착용해 보고",
    ProductCategory.WALLET: "직접 보고",
    ProductCategory.OUTERWEAR: "입어 보고",
    ProductCategory.ACCESSORY: "직접 보고",
}

#: 카테고리별 사이즈 근거 표현. "라스트" 는 구두 용어다.
SIZE_BASIS: dict[ProductCategory, str] = {
    ProductCategory.SHOES: "같은 라스트 계열",
    ProductCategory.BAG: "같은 사이즈 체계",
    ProductCategory.WATCH: "같은 케이스 규격",
    ProductCategory.BELT: "같은 길이 체계",
    ProductCategory.WALLET: "같은 규격",
    ProductCategory.OUTERWEAR: "같은 패턴",
    ProductCategory.ACCESSORY: "같은 규격",
}


@dataclass
class Citation:
    """인용할 개체와 문장 재료."""

    asset: OwnedAsset
    years: float
    same_category: bool

    @property
    def year_label(self) -> str:
        return f"{self.asset.purchased_at.year}년"

    @property
    def headline(self) -> str:
        return self.asset.findings[0].note if self.asset.findings else "특이 소견 없음"


def rank_assets(assets: list[OwnedAsset], target: Product) -> list[OwnedAsset]:
    """인용 우선순위. 같은 카테고리 → 서비스 임박 → 컨디션 낮은 순.

    같은 카테고리를 먼저 두는 이유: 사이즈·라스트·소재 이야기가 성립하는 근거이기 때문이다.
    """
    return sorted(
        assets,
        key=lambda a: (
            0 if a.category is target.category else 1,
            a.next_service_months,
            a.condition_score,
        ),
    )


def build_citations(request: ClientelingReplyRequest, strategy: Strategy) -> list[Citation]:
    """전략 정책에 따라 인용 목록을 만든다. S1/S3 은 빈 목록."""
    if not strategy.cite_assets or not request.owned_assets:
        return []
    ranked = rank_assets(list(request.owned_assets), request.target_product)
    # 1순위는 항상 인용한다. 2순위 이후는 **근거로서 의미가 있을 때만** 붙인다.
    # (컨디션이 충분히 좋고 카테고리도 다른 개체를 억지로 인용하면 문장이 설득력을 잃는다)
    picked = ranked[:1]
    for asset in ranked[1 : max(1, strategy.max_citations)]:
        relevant = (
            asset.next_service_months <= 6
            or asset.condition_score <= CARE_THRESHOLD + 5
            or asset.category is request.target_product.category
        )
        if relevant:
            picked.append(asset)
    return [
        Citation(
            asset=a,
            years=years_between(a.purchased_at, REFERENCE_NOW),
            same_category=a.category is request.target_product.category,
        )
        for a in picked
    ]


def evidence_sentence(citation: Citation) -> str:
    """소유 자산 근거 문장. 컨디션 점수와 소견을 반드시 포함한다."""
    asset = citation.asset
    span = f"{int(citation.years)}년" if citation.years >= 1 else "최근"
    if asset.condition_score <= CARE_THRESHOLD:
        state = f"컨디션 {asset.condition_score}점으로 케어 권장 구간에 들어왔습니다"
    elif asset.next_service_months <= 3:
        state = (
            f"컨디션 {asset.condition_score}점, 약 {asset.next_service_months}개월 뒤 "
            "케어 권장 시점입니다"
        )
    else:
        state = f"컨디션 {asset.condition_score}점으로 잘 관리되고 있습니다"
    return (
        f"{citation.year_label}에 함께하신 {asset.product_name}은 {span} 사용에 {state}"
        f"({citation.headline})."
    )


def _sizes_label(product: Product) -> str:
    return ", ".join(product.available_sizes) if product.available_sizes else "재고 확인 필요"


def resolution_sentence(
    hesitation: HesitationType,
    target: Product,
    citations: list[Citation],
    strategy: Strategy,
) -> str:
    """망설임 유형별 해소 문장. 인용이 있으면 그 근거를 이어 쓴다."""
    same = next((c for c in citations if c.same_category), None)

    if hesitation is HesitationType.SIZE_UNCERTAIN:
        if same is not None:
            return (
                f"{same.asset.product_name}과 {target.name}은 "
                f"{SIZE_BASIS[target.category]}입니다. 그때 맞춰 드린 치수를 그대로 적용하면 "
                f"편차가 거의 없습니다. "
                f"현재 준비된 사이즈는 {_sizes_label(target)}입니다."
            )
        return (
            f"{target.name}은 {target.size_system} 기준이고, 현재 {_sizes_label(target)} 사이즈가 "
            f"준비돼 있습니다. 매장에서 두 사이즈를 함께 "
            f"{TRY_VERB[target.category]} 결정하시는 편이 안전합니다."
        )

    if hesitation is HesitationType.PRICE_HESITANT:
        if citations:
            c = citations[0]
            per_year = (
                f"{c.asset.product_name}을 {int(c.years)}년 쓰신 지금도 컨디션 "
                f"{c.asset.condition_score}점입니다. 같은 제법이라 연 단위로 보면 "
                f"유지 비용이 낮습니다."
            )
            return per_year
        return (
            f"{target.price_krw:,}원은 {target.material} 제법 기준입니다. "
            f"케어를 전제로 하면 사용 연수가 길어 연 단위 비용은 완만해집니다."
        )

    if hesitation is HesitationType.STYLE_DOUBT:
        if citations:
            owned = ", ".join(dict.fromkeys(c.asset.product_name for c in citations))
            return (
                f"이미 보유하신 {owned}와 결이 이어지는 라인입니다. "
                f"{target.color} 컬러라 기존 조합과 충돌하지 않습니다."
            )
        return (
            f"{target.name}은 {target.collection} 컬렉션의 {target.color} 컬러이고 "
            f"{target.material} 소재입니다. 데일리와 격식 자리 모두 감당하는 형태입니다."
        )

    if hesitation is HesitationType.STOCK_CONCERN:
        available = _sizes_label(target)
        scarce = len(target.available_sizes) <= 2
        note = (
            "남은 수량이 적어 재입고 일정은 확정되지 않았습니다."
            if scarce
            else "현재 재고는 안정적으로 확보돼 있습니다."
        )
        return f"{target.name}의 현재 가용 사이즈는 {available}입니다. {note}"

    # NONE — 일반 제안
    if citations:
        return (
            f"기록을 보니 {citations[0].asset.product_name}을 오래 쓰고 계십니다. "
            f"{target.name}은 그 사용 패턴과 맞는 형태입니다."
        )
    return (
        f"{target.name}은 {target.collection} 컬렉션이며 {target.material} 소재입니다. "
        f"필요하신 부분을 말씀해 주시면 맞춰 안내하겠습니다."
    )


def scarcity_sentence(target: Product) -> str:
    if len(target.available_sizes) <= 2:
        return (
            f"현재 {_sizes_label(target)} 사이즈만 남아 있고, 이 컬러는 이번 컬렉션으로 종료됩니다."
        )
    return "이번 시즌 물량은 이미 상당 부분 배정됐고, 추가 입고는 확정되지 않았습니다."


def decide_cta(hesitation: HesitationType, citations: list[Citation], strategy: Strategy) -> CTA:
    """CTA 결정. 케어 시점이 임박한 인용이 있으면 케어 예약이 우선한다."""
    if citations and any(
        c.asset.condition_score <= CARE_THRESHOLD or c.asset.next_service_months <= 3
        for c in citations
    ):
        return CTA.CARE_BOOKING
    if hesitation is HesitationType.SIZE_UNCERTAIN:
        return CTA.BOOK_FITTING
    if hesitation is HesitationType.STOCK_CONCERN:
        return CTA.VIEW_STOCK
    return strategy.cta_preference


CTA_SENTENCE: dict[CTA, str] = {
    CTA.BOOK_FITTING: "가까운 부티크에서 피팅 시간을 잡아 드릴까요?",
    CTA.VIEW_STOCK: "원하시는 사이즈의 재고와 입고 일정을 확인해 드릴까요?",
    CTA.CARE_BOOKING: "케어 예약을 함께 잡아 드릴까요?",
    CTA.NONE: "",
}


def build_reply(request: ClientelingReplyRequest, strategy: Strategy) -> ClientelingReplyResponse:
    """전략 × 망설임 × 소유 자산으로 상담 응답을 조립한다(결정적)."""
    citations = build_citations(request, strategy)
    parts: list[str] = []

    if citations:
        parts.append(evidence_sentence(citations[0]))
    if strategy.scarcity_pressure >= 0.5:
        parts.append(scarcity_sentence(request.target_product))
    parts.append(
        resolution_sentence(request.hesitation_type, request.target_product, citations, strategy)
    )

    cta = decide_cta(request.hesitation_type, citations, strategy)
    tail = CTA_SENTENCE.get(cta, "")
    if tail:
        parts.append(tail)

    reasoning_bits = [
        f"전략 {strategy.id}({strategy.name})",
        f"망설임 {request.hesitation_type.value}",
    ]
    if citations:
        reasoning_bits.append(
            "인용 "
            + ", ".join(f"{c.asset.asset_id}({c.asset.condition_score}점)" for c in citations)
        )
    else:
        reasoning_bits.append(
            "인용 없음 — 전략 정책상 자산 미인용"
            if not strategy.cite_assets
            else "인용 없음 — 소유 개체 없음"
        )

    return ClientelingReplyResponse(
        message=" ".join(parts),
        cited_asset_ids=[c.asset.asset_id for c in citations],
        cta=cta,
        reasoning=" / ".join(reasoning_bits),
    )
