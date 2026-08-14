"""심판 — 대화 전문을 보고 전환 여부와 신뢰도를 판정한다.

**심판은 전략 id 를 보지 않는다.** 페르소나 파라미터와 대화 내용만 본다. 그래서 전략별 차이는
"전략이 만든 문구 차이"에서만 발생한다(특정 전략이 이기도록 하드코딩하지 않는다).

LLM 이 있으면 LLM 심판, 없으면 규칙 심판이다. 규칙 심판은 페르소나 봇이 턴마다 갱신한 신뢰도와
충족되지 못한 요구를 근거로 판정한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.lab.persona_bot import clamp_trust
from app.llm import LLMClient, Message
from app.personas import NEED_LABELS, Persona

#: 이탈 사유 코드. 대시보드의 이탈 사유 분포에 쓰인다.
DROP_REASONS: tuple[str, ...] = (
    "NO_EVIDENCE",  # 내 물건에 대한 근거가 없었다
    "PRICE",  # 가격이 정당화되지 않았다
    "SIZE_DOUBT",  # 사이즈 확신을 얻지 못했다
    "STYLE_DOUBT",  # 취향 적합성이 해소되지 않았다
    "PRESSURE",  # 압박이 불편했다
    "STOCK",  # 재고 불확실
    "NO_CTA",  # 다음 행동 제안이 없었다
    "TIMEOUT",  # 턴을 다 쓰고도 결정 못 함
    "",  # 전환됨
)

_NEED_TO_DROP: dict[str, str] = {
    "style_fit": "STYLE_DOUBT",
    "size_fit": "SIZE_DOUBT",
    "price_value": "PRICE",
    "care_cost": "NO_EVIDENCE",
    "resale_value": "NO_EVIDENCE",
    "relationship": "NO_EVIDENCE",
    "stock_certainty": "STOCK",
}


@dataclass
class Verdict:
    """세션 1건의 판정."""

    converted: bool
    turns_to_decision: int
    drop_reason: str
    trust_score: int
    reasoning: str
    source: str  # rule | llm

    def as_dict(self) -> dict[str, Any]:
        return {
            "converted": self.converted,
            "turns_to_decision": self.turns_to_decision,
            "drop_reason": self.drop_reason,
            "trust_score": self.trust_score,
            "reasoning": self.reasoning,
            "source": self.source,
        }


def rule_verdict(
    persona: Persona,
    trust: float,
    turns: int,
    unmet: list[str],
    pressure_seen: bool,
    cta_seen: bool,
    cited_any: bool,
) -> Verdict:
    """규칙 심판. 페르소나 파라미터와 대화에서 관측된 사실만 쓴다."""
    converted = trust >= persona.trust_threshold and cta_seen
    if converted:
        reason = ""
        note = f"신뢰도 {trust:.1f} ≥ 기준 {persona.trust_threshold} 이고 다음 행동 제안이 있었다"
    elif pressure_seen and persona.pressure_aversion >= 0.7 and trust < persona.trust_threshold:
        reason = "PRESSURE"
        note = "압박 표현이 신뢰를 깎았다"
    elif not cta_seen and trust >= persona.trust_threshold:
        reason = "NO_CTA"
        note = "설득은 됐지만 다음 행동 제안이 없어 결정으로 이어지지 않았다"
    elif unmet:
        reason = _NEED_TO_DROP.get(unmet[0], "NO_EVIDENCE")
        note = f"미해소 요구: {', '.join(NEED_LABELS.get(n, n) for n in unmet)}"
    elif not cited_any:
        reason = "NO_EVIDENCE"
        note = "소유 자산 근거가 한 번도 제시되지 않았다"
    else:
        reason = "TIMEOUT"
        note = f"턴을 모두 사용했으나 신뢰도 {trust:.1f} < 기준 {persona.trust_threshold}"

    return Verdict(
        converted=converted,
        turns_to_decision=turns,
        drop_reason=reason,
        trust_score=int(round(clamp_trust(trust))),
        reasoning=note,
        source="rule",
    )


JUDGE_SYSTEM = """당신은 상담 품질 심판이다. 고객과 어드바이저의 대화 전문을 읽고 판정한다.
전략 이름이나 시스템 내부 정보는 주어지지 않는다. 대화 내용과 고객의 판단 기준만 보고 판단하라.

JSON 하나만 출력한다:
{"converted": bool, "turns_to_decision": int, "drop_reason": str,
 "trust_score": int, "reasoning": str}

- converted: 고객이 예약/구매 등 다음 단계로 넘어갈 의사를 실제로 표현했는가
- turns_to_decision: 결정(또는 이탈)이 확정된 어드바이저 턴 번호(1부터)
- drop_reason: 전환됐으면 "", 아니면 NO_EVIDENCE / PRICE / SIZE_DOUBT / STYLE_DOUBT /
  PRESSURE / STOCK / NO_CTA / TIMEOUT 중 하나
- trust_score: 1~5 정수. 고객이 이 어드바이저를 신뢰하게 됐는지
- reasoning: 한 문장 근거"""


def llm_verdict(
    llm: LLMClient,
    persona: Persona,
    transcript: list[dict[str, str]],
    fallback: Verdict,
) -> Verdict:
    """LLM 심판. 파싱 실패나 미연결이면 규칙 판정을 그대로 쓴다."""
    if not llm.settings.llm_enabled:
        return fallback
    convo = "\n".join(f"{t['role']}: {t['content']}" for t in transcript)
    messages: list[Message] = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {
            "role": "user",
            "content": (
                f"[고객의 판단 기준]\n{persona.name} — 목표: {persona.goal}\n"
                f"중요하게 보는 것: {', '.join(persona.need_labels)}\n"
                f"가격 민감도 {persona.budget_sensitivity} / 근거 요구 {persona.evidence_need} / "
                f"압박 거부감 {persona.pressure_aversion}\n\n"
                f"[대화 전문]\n{convo}"
            ),
        },
    ]
    parsed = llm.complete_json(
        messages, fallback=lambda: fallback.as_dict(), cache=True, max_tokens=400
    )
    if not isinstance(parsed, dict):
        return fallback
    try:
        reason = str(parsed.get("drop_reason", "")).upper().strip()
        if reason not in DROP_REASONS:
            reason = "" if bool(parsed.get("converted")) else "TIMEOUT"
        trust = int(parsed.get("trust_score", fallback.trust_score))
        turns = int(parsed.get("turns_to_decision", fallback.turns_to_decision))
        return Verdict(
            converted=bool(parsed.get("converted")),
            turns_to_decision=max(1, turns),
            drop_reason="" if bool(parsed.get("converted")) else reason,
            trust_score=max(1, min(5, trust)),
            reasoning=str(parsed.get("reasoning", ""))[:400],
            source="llm",
        )
    except (TypeError, ValueError):
        return fallback


_TRANSCRIPT_ID_RE = re.compile(r"AS-\d{6}")


def cited_in_transcript(transcript: list[dict[str, str]]) -> list[str]:
    """대화 전문에서 인용된 개체 id (대시보드 표시용)."""
    found: list[str] = []
    for turn in transcript:
        for match in _TRANSCRIPT_ID_RE.findall(turn.get("content", "")):
            if match not in found:
                found.append(match)
    return found
