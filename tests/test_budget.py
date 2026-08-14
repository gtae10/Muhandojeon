"""예산 통제 검증 — 하드 리밋 거부, 드라이런, 캐시 키 안정성, 라우팅.

크레딧 100달러가 총액이고 초과 시 복구 수단이 없다. 이 파일의 테스트가 깨지면 예산 사고가
날 수 있으므로 실패를 무시하지 않는다.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.config import Settings
from app.data.provider import get_provider
from app.lab.persona_bot import PERSONA_SYSTEM
from app.llm import (
    BudgetExceeded,
    LLMClient,
    Message,
    estimate_tokens,
    load_capabilities,
    price_for,
    resolve,
    supports_vision,
)
from app.llm.budget import BudgetGuard, BudgetState


@pytest.fixture
def canned_post(monkeypatch):
    """성공 응답을 주는 httpx.post 스텁. 호출 횟수를 센다."""
    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        calls.append(kwargs)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "응답 문구"}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 60},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


def _client(tmp_path: Any, monkeypatch: Any, **overrides: Any) -> LLMClient:
    settings = Settings(
        llm_api_key="test-key",
        llm_base_url="http://llm.invalid/v1",
        upstream_retries=0,
        llm_models_discovery=False,
        **overrides,
    )
    client = LLMClient(settings)
    monkeypatch.setattr(client, "_cache_dir", tmp_path)
    return client


MESSAGES: list[Message] = [{"role": "user", "content": "상담 문구를 만들어라"}]


# ── 능력 플래그 (비전 부재 확정) ────────────────────────────────
def test_vision_is_disabled_by_config():
    caps = load_capabilities()
    assert caps["vision"] is False, "비전 부재가 확정이다. 이미지 경로를 만들면 안 된다"
    assert supports_vision() is False
    assert caps.get("embeddings") is False


def test_no_image_payload_in_any_prompt():
    """프롬프트에 이미지(base64/data URI)를 넣는 경로가 없어야 한다 — 실패하며 토큰만 태운다."""
    from app.adapters.clienteling import SYSTEM_PROMPT, build_prompt
    from app.lab.judge import JUDGE_SYSTEM

    texts = [SYSTEM_PROMPT, JUDGE_SYSTEM, PERSONA_SYSTEM]
    provider = get_provider()
    product = provider.get_products()[0]
    from contracts.clienteling import ClientelingReplyRequest
    from contracts.common import HesitationType

    request = ClientelingReplyRequest(
        customer_id="CU-0001",
        hesitation_type=HesitationType.SIZE_UNCERTAIN,
        target_product=product,
        owned_assets=provider.get_assets("CU-0001"),
        strategy_id="S2",
    )
    texts += [m["content"] for m in build_prompt(request, resolve_strategy())]
    for text in texts:
        assert "base64" not in text.lower()
        assert "data:image" not in text.lower()
        assert "image_url" not in text.lower()


def resolve_strategy():
    from app.strategies import get_strategy

    return get_strategy("S2")


# ── 라우팅·단가 ───────────────────────────────────────────────
@pytest.mark.parametrize(
    ("purpose", "tier"),
    [
        ("clienteling", "high"),
        ("judge", "high"),
        ("persona", "low"),
        ("intent", "low"),
        ("condition_note", "low"),
        ("other", "low"),
    ],
)
def test_purpose_tier_routing(purpose, tier):
    """페르소나를 저가 티어로 내리는 것이 가장 큰 절감이다 — 정책이 코드에 반영됐는지 고정한다."""
    route = resolve(purpose)
    assert route.tier == tier
    assert route.model


def test_unknown_model_falls_back_to_conservative_pricing():
    price = price_for("some-unlisted-model-v9")
    assert price.source == "default"
    assert price.input_per_1m >= 1.0, "미등록 모델은 과소 추정하지 않아야 한다"
    known = price_for("gpt-4o-mini")
    assert known.source == "gpt-4o-mini"
    assert known.cost_usd(1_000_000, 0) == pytest.approx(0.15)


def test_token_estimate_handles_korean():
    assert estimate_tokens("") == 0
    korean = estimate_tokens("컨디션 71점 핸들 마모")
    ascii_text = estimate_tokens("condition 71 handle wear")
    assert korean > 0 and ascii_text > 0
    # 같은 의미의 한국어가 토큰을 더 많이 쓴다(문자당 토큰이 촘촘하다).
    assert korean >= ascii_text / 2


# ── 예산 게이트 ───────────────────────────────────────────────
def test_hard_limit_refuses_call_before_spending(tmp_path, monkeypatch, canned_post):
    """하드 리밋을 넘길 호출은 **실행하지 않는다**(사후 집계로는 늦다)."""
    client = _client(tmp_path, monkeypatch, llm_budget_hard_usd=0.0, llm_cache_enabled=False)
    text = client.complete(MESSAGES, purpose="clienteling", fallback=lambda: "결정적 폴백")
    assert text == "결정적 폴백"
    assert canned_post == [], "거부된 호출이 실제로 나가면 안 된다"
    assert client.stats.refusals == 1


def test_call_proceeds_when_budget_available(tmp_path, monkeypatch, canned_post):
    client = _client(tmp_path, monkeypatch, llm_cache_enabled=False)
    text = client.complete(MESSAGES, purpose="clienteling", fallback=lambda: "폴백")
    assert text == "응답 문구"
    assert len(canned_post) == 1
    assert client.stats.calls == 1


def test_dry_run_never_calls_but_estimates(tmp_path, monkeypatch, canned_post):
    client = _client(tmp_path, monkeypatch, llm_dry_run=True)
    text = client.complete(MESSAGES, purpose="persona", fallback=lambda: "폴백")
    assert text == "폴백"
    assert canned_post == []
    assert client.stats.dry_runs == 1
    assert client.settings.llm_active is True, "드라이런은 키 없이도 LLM 경로를 타야 추정이 된다"


def test_budget_state_levels():
    state = BudgetState(spent_usd=10.0, total_usd=100.0, warn_usd=60.0, hard_usd=85.0)
    assert state.level == "ok"
    assert state.remaining_to_hard == pytest.approx(75.0)
    assert BudgetState(70.0, 100.0, 60.0, 85.0).level == "warn"
    assert BudgetState(90.0, 100.0, 60.0, 85.0).level == "hard"
    assert BudgetState(90.0, 100.0, 60.0, 85.0).remaining_to_hard == 0.0


def test_guard_raises_only_over_hard_limit(monkeypatch):
    guard = BudgetGuard()
    monkeypatch.setattr(guard, "_load_spent", lambda: 80.0)
    guard.invalidate()
    guard.check_before_call("persona", "gpt-4o-mini", 1.0)  # 81 < 85 → 통과
    with pytest.raises(BudgetExceeded):
        guard.check_before_call("clienteling", "gpt-4o", 10.0)  # 90 > 85 → 거부


# ── 캐시 ─────────────────────────────────────────────────────
def test_cache_hit_avoids_second_call(tmp_path, monkeypatch, canned_post):
    client = _client(tmp_path, monkeypatch)
    first = client.complete(MESSAGES, purpose="judge", fallback=lambda: "폴백")
    second = client.complete(MESSAGES, purpose="judge", fallback=lambda: "폴백")
    assert first == second == "응답 문구"
    assert len(canned_post) == 1, "두 번째 호출은 캐시에서 나와야 한다"
    assert client.stats.cache_hits == 1


def test_cache_key_changes_with_model_and_temperature(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    base = client.cache_key(MESSAGES, "gpt-4o-mini", 0.0)
    assert base != client.cache_key(MESSAGES, "gpt-4o", 0.0), "모델을 바꾸면 캐시가 무효화돼야 한다"
    assert base != client.cache_key(MESSAGES, "gpt-4o-mini", 0.7)
    assert base == client.cache_key(MESSAGES, "gpt-4o-mini", 0.0)


def test_prompts_are_deterministic_across_builds():
    """프롬프트에 현재 시각·UUID 가 섞이면 캐시가 매 실행 무효화된다(예산 사고 1순위)."""
    from app.adapters.clienteling import build_prompt
    from app.demo import build_request, load_scenarios
    from app.lab.runner import simulate_session
    from app.personas import load_personas
    from contracts.clienteling import ClientelingReplyRequest
    from contracts.common import HesitationType

    provider = get_provider()
    request = ClientelingReplyRequest(
        customer_id="CU-0001",
        hesitation_type=HesitationType.STOCK_CONCERN,
        target_product=provider.get_products()[1],
        owned_assets=provider.get_assets("CU-0001"),
        strategy_id="S2",
    )
    first = build_prompt(request, resolve_strategy())
    second = build_prompt(request, resolve_strategy())
    assert first == second

    # 데모 시나리오 요청도 두 번 만들어 동일해야 한다(세션 선택·이벤트 고정).
    scenario = load_scenarios()["D1"]
    assert build_request(scenario).model_dump() == build_request(scenario).model_dump()

    # Lab 세션도 같은 (페르소나, 전략, 회차) 면 같은 대화가 나와야 한다.
    persona = load_personas()["P3"]
    a = simulate_session(persona, "S2", iteration=0, max_turns=3)
    b = simulate_session(persona, "S2", iteration=0, max_turns=3)
    assert [t["content"] for t in a.transcript] == [t["content"] for t in b.transcript]
