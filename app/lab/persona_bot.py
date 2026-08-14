"""페르소나 봇 — 고객 역할.

두 모드가 있다.
1. LLM 이 연결돼 있으면 페르소나 프롬프트로 고객 발화를 생성한다.
2. 없으면 **규칙 기반 봇**이 상담 문구의 내용을 보고 반응한다.

규칙 봇의 판단은 **전략 id 를 보지 않는다.** 상담 문구에 무엇이 담겼는지(소유 자산 인용,
컨디션 수치, 케어 언급, 가격 근거, 희소성 압박)와 페르소나 파라미터만으로 신뢰도를 갱신한다.
전략별 결과 차이는 그래서 "전략이 실제로 만든 문구 차이"에서만 나온다. 특정 전략이 이기도록
하드코딩하지 않는다는 뜻이다(명세의 하드 룰).

LLM 이 없을 때 이 Lab 이 측정하는 것은 "언어 모델의 설득력"이 아니라 **"규칙 모델 상의 전략 효과"**
라는 한계가 있다. 대시보드와 보고에 그대로 표시한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.llm import LLMClient, Message
from app.personas import NEED_LABELS, Persona
from contracts.clienteling import ClientelingReplyResponse
from contracts.common import CTA

TRUST_MIN, TRUST_MAX = 1.0, 5.0
TRUST_START = 3.0

_RE_CONDITION = re.compile(r"컨디션\s*\d{1,3}\s*점")
_RE_PRICE = re.compile(r"\d{1,3}(?:,\d{3})+\s*원")
_RE_YEAR = re.compile(r"\d{4}년")

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "care": ("케어", "보습", "재코팅", "오버홀", "재밑창", "클리닝", "점검"),
    "size": ("사이즈", "치수", "라스트", "규격", "길이 체계", "케이스"),
    "stock": ("재고", "입고", "가용", "남아"),
    "pressure": ("종료", "재입고", "확정되지 않", "남아 있", "배정"),
    "value": ("유지 비용", "연 단위", "제법", "사용 연수", "오래"),
    "style": ("컬러", "컬렉션", "소재", "조합", "결이", "라인"),
}


@dataclass
class MessageFeatures:
    """상담 문구에서 뽑은 사실들. 규칙 봇과 심판이 공유한다."""

    cites_asset: bool
    condition_evidence: bool
    purchase_year: bool
    mentions_care: bool
    mentions_size: bool
    mentions_stock: bool
    mentions_price: bool
    value_framing: bool
    style_framing: bool
    pressure: bool
    cta: CTA
    cited_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "cites_asset": self.cites_asset,
            "condition_evidence": self.condition_evidence,
            "mentions_care": self.mentions_care,
            "mentions_size": self.mentions_size,
            "mentions_stock": self.mentions_stock,
            "mentions_price": self.mentions_price,
            "value_framing": self.value_framing,
            "pressure": self.pressure,
            "cta": self.cta.value,
            "cited_ids": self.cited_ids,
        }


def _has(text: str, key: str) -> bool:
    return any(word in text for word in _KEYWORDS[key])


def extract_features(reply: ClientelingReplyResponse) -> MessageFeatures:
    """상담 응답에서 판단 근거가 될 사실만 뽑는다(전략 id 는 보지 않는다)."""
    text = reply.message
    return MessageFeatures(
        cites_asset=bool(reply.cited_asset_ids),
        condition_evidence=bool(_RE_CONDITION.search(text)),
        purchase_year=bool(_RE_YEAR.search(text)),
        mentions_care=_has(text, "care"),
        mentions_size=_has(text, "size"),
        mentions_stock=_has(text, "stock"),
        mentions_price=bool(_RE_PRICE.search(text)),
        value_framing=_has(text, "value"),
        style_framing=_has(text, "style"),
        pressure=_has(text, "pressure"),
        cta=reply.cta,
        cited_ids=list(reply.cited_asset_ids),
    )


#: needs 키 → 그 요구가 충족됐다고 볼 조건
def needs_met(feats: MessageFeatures) -> set[str]:
    met: set[str] = set()
    if feats.style_framing:
        met.add("style_fit")
    if feats.mentions_size:
        met.add("size_fit")
    if feats.value_framing or (feats.mentions_price and feats.value_framing):
        met.add("price_value")
    if feats.mentions_care:
        met.add("care_cost")
    if feats.cites_asset and feats.condition_evidence:
        met.add("resale_value")
        met.add("relationship")
    if feats.mentions_stock:
        met.add("stock_certainty")
    return met


@dataclass
class TurnEvaluation:
    """한 턴에 대한 고객의 내부 반응."""

    delta: float
    reasons: list[str]
    met: set[str]


def evaluate_turn(
    persona: Persona,
    feats: MessageFeatures,
    *,
    already_met: set[str] | None = None,
    evidence_seen: bool = False,
) -> TurnEvaluation:
    """상담 문구가 이 페르소나에게 어떻게 작용하는지 계산한다.

    **같은 근거의 반복은 새 정보가 아니다.** 이미 본 근거는 30% 만 반영하고, 이미 충족된 요구는
    다시 가산하지 않는다(그렇게 하지 않으면 턴 수만으로 신뢰가 무한히 오른다).
    """
    reasons: list[str] = []
    delta = 0.0
    seen = already_met or set()
    repeat_factor = 0.3 if evidence_seen else 1.0

    if feats.cites_asset and feats.condition_evidence:
        gain = 0.9 * persona.evidence_need * repeat_factor
        delta += gain
        suffix = " (반복 제시)" if evidence_seen else ""
        reasons.append(f"내 개체와 컨디션 수치를 근거로 제시{suffix} (+{gain:.2f})")
    elif feats.cites_asset:
        gain = 0.4 * persona.evidence_need * repeat_factor
        delta += gain
        reasons.append(f"내 개체를 언급했으나 수치 근거는 약함 (+{gain:.2f})")
    else:
        loss = 0.35 * persona.evidence_need
        delta -= loss
        reasons.append(f"내 물건에 대한 언급 없음 (-{loss:.2f})")

    met = needs_met(feats)
    newly = [n for n in persona.needs if n in met and n not in seen]
    for need in newly:
        delta += 0.45
        reasons.append(f"요구 충족: {NEED_LABELS.get(need, need)} (+0.45)")

    if feats.pressure:
        loss = 0.8 * persona.pressure_aversion
        delta -= loss
        reasons.append(f"희소성/타이밍 압박 (-{loss:.2f})")

    if feats.mentions_price and not feats.value_framing:
        loss = 0.5 * persona.budget_sensitivity
        delta -= loss
        reasons.append(f"가격만 제시되고 가치 근거 없음 (-{loss:.2f})")

    if feats.cta is not CTA.NONE:
        delta += 0.15
        reasons.append("다음 행동 제안 있음 (+0.15)")

    delta += 0.1 * persona.brand_familiarity
    return TurnEvaluation(delta=round(delta, 3), reasons=reasons, met=met)


def customer_reply(
    persona: Persona,
    feats: MessageFeatures,
    trust: float,
    turn: int,
    unmet: list[str],
) -> str:
    """규칙 기반 고객 발화. 남은 의문을 그대로 되묻는다."""
    if trust >= persona.trust_threshold:
        if feats.cta is CTA.CARE_BOOKING:
            return "케어까지 같이 봐 주시면 좋겠어요. 그렇게 진행해 주세요."
        if feats.cta is CTA.BOOK_FITTING:
            return "그러면 방문해서 직접 확인하고 결정할게요. 예약 부탁드려요."
        if feats.cta is CTA.VIEW_STOCK:
            return "재고 확인해 주시면 그걸 보고 결정할게요."
        return "설명 들으니 정리가 됐어요. 진행하는 쪽으로 생각해 볼게요."

    if feats.pressure and persona.pressure_aversion >= 0.7:
        return "재고가 없다는 식으로 재촉하시면 오히려 결정을 못 하겠어요."

    if unmet:
        need = unmet[0]
        prompts = {
            "style_fit": "제 스타일과 실제로 맞는지, 근거를 들어 설명해 주실 수 있나요?",
            "size_fit": "제 기준으로 어떤 사이즈가 맞는지 알 수 있을까요?",
            "price_value": "이 가격이 합당한 이유를 좀 더 구체적으로 알고 싶어요.",
            "care_cost": "관리 비용은 어느 정도이고, 얼마나 오래 쓸 수 있나요?",
            "resale_value": "지금 제가 가진 것들의 상태 기준으로 봐 주시면 좋겠어요.",
            "stock_certainty": "지금 재고 상황을 정확히 알려 주세요.",
            "relationship": "제가 어떤 걸 갖고 있는지 보고 말씀하시는 건가요?",
        }
        return prompts.get(need, "조금 더 구체적으로 설명해 주실 수 있나요?")

    if turn >= persona.patience_turns - 1:
        return "일단 더 생각해 보고 다시 연락드릴게요."
    return "음, 아직 확신이 안 서요. 다른 근거가 있을까요?"


PERSONA_SYSTEM = """당신은 럭셔리 브랜드 고객이다. 어드바이저와 상담하는 중이다.
주어진 성격·목표·판단 기준에 맞게 **고객으로서** 한두 문장만 말한다.
규칙:
1. 한국어. 1~2문장. 고객다운 어조를 유지한다.
2. 근거 없이 설득되지 않는다. 아직 해소되지 않은 의문이 있으면 그것을 되묻는다.
3. 충분히 납득되면 결정을 말한다(예약/구매 의사).
4. 어드바이저 역할을 하지 않는다. 제품 정보를 스스로 만들어내지 않는다."""


def llm_customer_reply(
    llm: LLMClient,
    persona: Persona,
    advisor_message: str,
    history: list[tuple[str, str]],
    trust: float,
    unmet: list[str],
    run_id: str | None = None,
) -> str | None:
    """LLM 페르소나 봇. 실패하면 None(호출자가 규칙 봇으로 폴백).

    **저가 티어**로 라우팅된다(config/model_routing.yaml). 고객 역할 연기는 품질 요구가 낮고
    Lab 호출의 절반이 이쪽이라 절감 효과가 가장 크다.
    """
    if not llm.settings.llm_active:
        return None
    convo = "\n".join(f"{role}: {content}" for role, content in history)
    unmet_labels = ", ".join(NEED_LABELS.get(n, n) for n in unmet) or "없음"
    messages: list[Message] = [
        {"role": "system", "content": PERSONA_SYSTEM},
        {
            "role": "user",
            "content": (
                f"[내 성격]\n{persona.name} — {persona.tone}\n목표: {persona.goal}\n"
                f"판단 기준: {', '.join(persona.need_labels)}\n"
                f"가격 민감도 {persona.budget_sensitivity} / 근거 요구 {persona.evidence_need} / "
                f"압박 거부감 {persona.pressure_aversion}\n"
                f"현재 신뢰도 {trust:.1f}/5 (전환 필요 {persona.trust_threshold})\n"
                f"아직 해소되지 않은 요구: {unmet_labels}\n\n"
                f"[대화]\n{convo}\n어드바이저: {advisor_message}\n\n"
                f"이제 고객으로서 대답하라(1~2문장, 설명 없이 발화만)."
            ),
        },
    ]
    text = llm.complete(
        messages, purpose="persona", fallback=lambda: "", max_tokens=200, run_id=run_id
    )
    return text.strip() or None


def clamp_trust(value: float) -> float:
    return max(TRUST_MIN, min(TRUST_MAX, round(value, 3)))
