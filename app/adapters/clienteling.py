"""상담 어댑터 (AI2).

목 구현은 두 경로를 갖는다.
1. `LLM_API_KEY` 가 있으면 OpenAI 호환 엔드포인트로 상담 문구를 생성한다(전략 지시문 주입).
2. 없거나 실패하면 `app/clienteling_rules.py` 의 결정적 템플릿으로 같은 스키마를 만든다.

두 경로 모두 **전략의 인용 정책을 따른다.** S2 는 소유 개체를 인용하고 S1/S3 은 인용하지 않는다.
LLM 이 S2 에서 인용을 빠뜨리면 그 결과를 그대로 둔다(인용을 사후에 끼워 넣으면 Persona Bot Lab
의 측정이 무의미해진다). 오케스트레이터가 `owned_assets_used=false` 로 드러낸다.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from app.adapters.base import AdapterBase
from app.adapters.http_base import HttpAdapterBase
from app.clienteling_rules import build_reply
from app.llm import LLMClient, Message, get_llm
from app.strategies import Strategy, get_strategy
from contracts.clienteling import ClientelingReplyRequest, ClientelingReplyResponse
from contracts.common import CTA

ASSET_ID_RE = re.compile(r"AS-\d{6}")

SYSTEM_PROMPT = """당신은 럭셔리 메종의 시니어 클라이언텔링 어드바이저다.
고객의 구매 망설임을 해소하는 짧은 상담 문구를 만든다.

공통 규칙
1. 한국어, 2~4문장. 과장 광고 표현을 쓰지 않는다.
2. 사실만 말한다. 주어진 데이터에 없는 재고·가격·일정을 만들어내지 않는다.
3. 실존 브랜드명을 언급하지 않는다.
4. 반드시 JSON 하나만 출력한다:
   {"message": str, "cited_asset_ids": [str], "cta": "BOOK_FITTING|VIEW_STOCK|CARE_BOOKING|NONE",
    "reasoning": str}
5. cited_asset_ids 에는 실제로 문장에서 근거로 삼은 개체 id 만 담는다. 없으면 빈 배열."""


def _asset_lines(request: ClientelingReplyRequest) -> str:
    lines = []
    for asset in request.owned_assets:
        findings = "; ".join(f"{f.part.value} {f.severity.value} {f.note}" for f in asset.findings)
        lines.append(
            f"- {asset.asset_id} | {asset.product_name} ({asset.category.value}) | "
            f"구매 {asset.purchased_at.date()} | 컨디션 {asset.condition_score}점 | "
            f"케어까지 {asset.next_service_months}개월 | 소견: {findings or '없음'}"
        )
    return "\n".join(lines) if lines else "(등록된 소유 개체 없음)"


def build_prompt(request: ClientelingReplyRequest, strategy: Strategy) -> list[Message]:
    """전략 지시문 + 대상 상품 + 소유 개체를 주입한 프롬프트."""
    product = request.target_product
    history = "\n".join(f"{turn.role.value}: {turn.content}" for turn in request.history)
    citation_rule = (
        f"이 전략은 소유 자산을 근거로 써야 한다. cited_asset_ids 에 최대 "
        f"{max(1, strategy.max_citations)}개를 담아라."
        if strategy.cite_assets
        else "이 전략은 소유 자산을 언급하지 않는다. cited_asset_ids 는 빈 배열로 둔다."
    )
    user = f"""[전략 {strategy.id} — {strategy.name}]
{strategy.instructions}
어조: {strategy.tone}
{citation_rule}

[고객]
customer_id: {request.customer_id}
망설임 유형: {request.hesitation_type.value}

[소유 개체 — 인용 우선순위 순]
{_asset_lines(request)}

[상담 대상 상품]
{product.name} ({product.collection}) / {product.category.value}
소재: {product.material} / 컬러: {product.color}
가격: {product.price_krw:,}원
사이즈 체계: {product.size_system}
현재 재고 사이즈: {", ".join(product.available_sizes) or "재고 확인 필요"}
케어: {product.care_notes}

[직전 대화]
{history or "(없음)"}
"""
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def parse_llm_reply(
    raw: Any, request: ClientelingReplyRequest, strategy: Strategy
) -> ClientelingReplyResponse | None:
    """LLM JSON 을 계약으로 변환한다. 소유하지 않은 개체 id 는 제거한다(환각 방지)."""
    if not isinstance(raw, dict):
        return None
    message = str(raw.get("message") or "").strip()
    if not message:
        return None
    owned = {a.asset_id for a in request.owned_assets}
    cited_raw = raw.get("cited_asset_ids") or []
    cited = [str(x) for x in cited_raw if str(x) in owned] if isinstance(cited_raw, list) else []
    # 문장 안에 개체 id 를 적어 놓고 필드는 비운 경우를 보완한다(있는 사실만 인정).
    for found in ASSET_ID_RE.findall(message):
        if found in owned and found not in cited:
            cited.append(found)
    if not strategy.cite_assets:
        cited = []
    try:
        cta = CTA(str(raw.get("cta", CTA.NONE.value)))
    except ValueError:
        cta = CTA.NONE
    return ClientelingReplyResponse(
        message=message,
        cited_asset_ids=cited[: max(1, strategy.max_citations)] if cited else [],
        cta=cta,
        reasoning=str(raw.get("reasoning") or "")[:500],
    )


class MockClientelingAdapter(AdapterBase):
    """LLM(있으면) + 결정적 템플릿(폴백) 상담 생성."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or get_llm()
        mode_target = (
            f"LLM {self.llm.settings.llm_model}"
            if self.llm.settings.llm_enabled
            else "app.clienteling_rules (템플릿)"
        )
        super().__init__(module="clienteling", mode="mock", target=mode_target)

    def reply(self, request: ClientelingReplyRequest) -> ClientelingReplyResponse:
        started = time.perf_counter()
        strategy = get_strategy(request.strategy_id)
        template = build_reply(request, strategy)

        if not self.llm.settings.llm_active:
            elapsed = (time.perf_counter() - started) * 1000
            self.status.record_success(
                elapsed, f"template {strategy.id} / 인용 {len(template.cited_asset_ids)}건"
            )
            return template

        parsed = self.llm.complete_json(
            build_prompt(request, strategy),
            purpose="clienteling",
            fallback=lambda: json.loads(template.model_dump_json()),
            # 상담 문구는 2~4문장 + JSON 필드다. 상한을 조여야 예산 게이트의 추정이 정확해지고
            # 모델이 길게 늘어지는 사고도 막는다.
            max_tokens=400,
        )
        result = parse_llm_reply(parsed, request, strategy) or template
        elapsed = (time.perf_counter() - started) * 1000
        source = "llm" if result is not template else "template"
        self.status.record_success(
            elapsed, f"{source} {strategy.id} / 인용 {len(result.cited_asset_ids)}건"
        )
        return result


def legacy_clienteling_mapper(raw: Any) -> dict[str, Any]:
    """팀 백엔드의 `POST /api/chat` 응답을 계약으로 옮긴다.

    그 응답에는 `cited_asset_ids` / `cta` 가 없다(= 우리 차별점을 측정할 수 없다).
    문장 안의 `AS-xxxxxx` 패턴만 최선으로 회수하고, 나머지는 비운 채 넘긴다.
    백엔드가 채워야 할 항목은 `docs/BACKEND_INTEGRATION.md` 에 정리해 두었다.
    """
    if not isinstance(raw, dict):
        raise TypeError(f"dict 가 아님: {type(raw)}")
    message = str(raw.get("message") or raw.get("reply") or "").strip()
    cited = raw.get("cited_asset_ids")
    if not isinstance(cited, list) or not cited:
        cited = ASSET_ID_RE.findall(message)
    try:
        cta = CTA(str(raw.get("cta", CTA.NONE.value))).value
    except ValueError:
        cta = CTA.NONE.value
    return {
        "message": message,
        "cited_asset_ids": [str(x) for x in cited],
        "cta": cta,
        "reasoning": str(raw.get("reasoning") or raw.get("model_used") or ""),
    }


class HttpClientelingAdapter(HttpAdapterBase):
    """실제 AI2 서버 호출 (`CLIENTELING_BASE_URL`). 계약 경로 → `/api/chat` 순으로 시도."""

    def __init__(self) -> None:
        super().__init__(module="clienteling")

    def reply(self, request: ClientelingReplyRequest) -> ClientelingReplyResponse:
        from app.adapters.base import UpstreamError

        payload = request.model_dump(mode="json")
        try:
            return self.post_model(
                "/clienteling/reply",
                payload,
                ClientelingReplyResponse,
                legacy_mapper=legacy_clienteling_mapper,
            )
        except UpstreamError:
            # 백엔드 `ChatRequest` 는 user_id 와 session_id 를 **둘 다** 필수로 받는다
            # (backend/app/schemas/models.py). 계약 요청에는 세션 id 가 없어 고객 id 를
            # 양쪽에 넣는다 — 백엔드는 세션 id 를 대화 이력 키로만 쓴다.
            legacy_payload = {
                "user_id": request.customer_id,
                "session_id": request.customer_id,
                "message": request.history[-1].content if request.history else "상담 요청",
                "product_id": request.target_product.product_id,
                "history": [t.model_dump(mode="json") for t in request.history],
            }
            return self.post_model(
                "/api/chat",
                legacy_payload,
                ClientelingReplyResponse,
                legacy_mapper=legacy_clienteling_mapper,
            )


def fallback_clienteling(request: ClientelingReplyRequest) -> ClientelingReplyResponse:
    """업스트림 실패 시 결정적 템플릿으로 대체한다. 화면에 에러를 노출하지 않기 위한 방어선."""
    strategy = get_strategy(request.strategy_id)
    result = build_reply(request, strategy)
    return result.model_copy(update={"reasoning": f"{result.reasoning} / degraded-fallback"})
