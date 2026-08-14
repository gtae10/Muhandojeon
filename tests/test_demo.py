"""데모 안정화 검증 — 시나리오 재현성, LLM 디스크 캐시, degraded 처리."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo import build_request, check_expectations, load_scenarios, pick_session
from app.llm import LLMClient, Message
from app.main import app
from app.services.orchestrator import Orchestrator


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_scenarios_are_pinned_and_pass_expectations():
    scenarios = load_scenarios()
    assert len(scenarios) == 3
    orchestrator = Orchestrator()
    for scenario in scenarios.values():
        result = orchestrator.advise(build_request(scenario))
        problems = check_expectations(scenario, result)
        assert problems == [], f"{scenario.id} 기대값 위반: {problems}"


def test_same_scenario_gives_same_flow():
    """같은 시나리오를 두 번 돌리면 같은 결과가 나와야 한다(발표 대본 보호)."""
    scenario = load_scenarios()["D3"]
    orchestrator = Orchestrator()
    first = orchestrator.advise(build_request(scenario))
    second = orchestrator.advise(build_request(scenario))
    assert first.message == second.message
    assert first.cited_asset_ids == second.cited_asset_ids
    assert first.cta == second.cta
    # 세션 선택도 고정이어야 한다.
    assert pick_session(scenario) is pick_session(scenario)


def test_demo_endpoint_reports_check_result(client):
    res = client.post("/demo/scenarios/D3/run")
    assert res.status_code == 200
    body = res.json()
    assert body["check"]["passed"] is True, body["check"]["problems"]
    assert res.headers["X-Demo-Check"] == "pass"
    assert res.headers["X-Degraded"] == "false"
    # 데모 대본의 핵심: 컨디션 71점 개체 인용
    assert 71 in [c["condition_score"] for c in body["response"]["citations"]]


def test_unknown_scenario_is_404(client):
    assert client.post("/demo/scenarios/NOPE/run").status_code == 404


def test_llm_disk_cache_survives_network_loss(tmp_path, monkeypatch):
    """DEMO_MODE 캐시: 한 번 받은 응답은 네트워크가 끊겨도 그대로 나온다."""
    settings = Settings(
        llm_api_key="test-key",
        llm_base_url="http://llm.invalid/v1",
        demo_mode=True,
        upstream_retries=0,
    )
    client = LLMClient(settings)
    monkeypatch.setattr(client, "_cache_dir", tmp_path)

    calls: list[dict[str, Any]] = []

    def fake_post(url: str, **kwargs: Any) -> httpx.Response:
        calls.append(kwargs)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "캐시된 상담 문구"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    messages: list[Message] = [{"role": "user", "content": "안녕"}]
    first = client.complete(messages, fallback=lambda: "폴백")
    assert first == "캐시된 상담 문구"
    assert len(calls) == 1
    assert client.cache_count() == 1

    # 네트워크가 끊긴 상황을 만든다 — 캐시가 있으면 호출조차 하지 않는다.
    def dead_post(url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("network down", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", dead_post)
    second = client.complete(messages, fallback=lambda: "폴백")
    assert second == "캐시된 상담 문구"
    assert client.stats.cache_hits == 1


def test_llm_failure_falls_back_without_raising(tmp_path, monkeypatch):
    settings = Settings(
        llm_api_key="test-key",
        llm_base_url="http://llm.invalid/v1",
        demo_mode=False,
        upstream_retries=0,
    )
    client = LLMClient(settings)
    monkeypatch.setattr(client, "_cache_dir", tmp_path)

    def dead_post(url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("network down", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", dead_post)
    text = client.complete([{"role": "user", "content": "x"}], fallback=lambda: "결정적 폴백")
    assert text == "결정적 폴백"
    assert client.stats.fallbacks == 1
    assert client.stats.errors


def test_health_detail_exposes_switches(client):
    detail = client.get("/health/detail").json()
    assert detail["status"] == "ok"
    modules = {a["module"] for a in detail["adapters"]}
    assert modules == {"intent", "clienteling", "asset", "fingerprint", "condition"}
    assert detail["demo"]["scenarios"] == 3
    assert detail["data"]["products"] == 12
    assert detail["data"]["seed_source"] == "fixture"
    assert "llm" in detail and "cache_entries" in detail["llm"]
