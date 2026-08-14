"""Persona Bot Lab 검증 — 결과 무결성(전략 id 비노출)과 하네스 동작."""

from __future__ import annotations

import inspect

import pytest

from app.lab import judge as judge_mod
from app.lab.judge import rule_verdict
from app.lab.persona_bot import (
    TRUST_START,
    evaluate_turn,
    extract_features,
)
from app.lab.runner import LabConfig, simulate_session
from app.lab.summary import summarize
from app.personas import load_personas, validate_bindings
from contracts.clienteling import ClientelingReplyResponse
from contracts.common import CTA


@pytest.fixture
def personas():
    return load_personas()


def test_personas_bind_to_real_customers_with_assets():
    problems = validate_bindings()
    assert problems == [], f"페르소나 바인딩 문제: {problems}"
    personas = load_personas()
    assert len(personas) == 5
    # 티어별로 골라야 P1(NEW)~P5(VIP) 시나리오가 성립한다.
    assert {p.customer_id for p in personas.values()} == {
        "CU-0030",
        "CU-0016",
        "CU-0014",
        "CU-0004",
        "CU-0001",
    }


def test_judge_and_persona_bot_never_see_strategy():
    """전략 id 가 판정 함수에 들어가면 결과를 조작할 여지가 생긴다 — 시그니처로 막는다."""
    for func in (rule_verdict, evaluate_turn, extract_features):
        params = set(inspect.signature(func).parameters)
        assert not {"strategy", "strategy_id"} & params, f"{func.__name__} 이 전략을 받는다"
    source = inspect.getsource(judge_mod)
    assert "strategy_id" not in source, "심판 모듈이 전략 id 를 참조한다"


def test_evidence_increases_trust_more_than_no_evidence(personas):
    persona = personas["P4"]  # evidence_need 0.95
    with_evidence = ClientelingReplyResponse(
        message="2023년에 함께하신 Aurelia Oxford는 컨디션 71점입니다. 케어를 함께 잡아 드릴까요?",
        cited_asset_ids=["AS-000031"],
        cta=CTA.CARE_BOOKING,
    )
    without = ClientelingReplyResponse(
        message="이 제품은 박스카프 카프스킨이고 재고가 있습니다.",
        cited_asset_ids=[],
        cta=CTA.VIEW_STOCK,
    )
    good = evaluate_turn(persona, extract_features(with_evidence))
    bad = evaluate_turn(persona, extract_features(without))
    assert good.delta > bad.delta
    assert bad.delta < 0


def test_repeated_evidence_has_diminishing_returns(personas):
    """같은 근거를 반복해도 신뢰가 계속 오르면 턴 수만으로 전환되어 측정이 무의미해진다."""
    persona = personas["P5"]
    reply = ClientelingReplyResponse(
        message="2022년의 Nocturne Shoulder는 컨디션 71점입니다. 케어 예약을 잡아 드릴까요?",
        cited_asset_ids=["AS-000001"],
        cta=CTA.CARE_BOOKING,
    )
    feats = extract_features(reply)
    first = evaluate_turn(persona, feats)
    repeat = evaluate_turn(persona, feats, already_met=first.met, evidence_seen=True)
    assert repeat.delta < first.delta


def test_pressure_penalizes_pressure_averse_persona(personas):
    persona = personas["P1"]  # pressure_aversion 0.85
    pressured = ClientelingReplyResponse(
        message="현재 36 사이즈만 남아 있고 이 컬러는 이번 컬렉션으로 종료됩니다.",
        cited_asset_ids=[],
        cta=CTA.VIEW_STOCK,
    )
    assert evaluate_turn(persona, extract_features(pressured)).delta < 0


def test_simulate_session_produces_transcript_and_verdict(personas):
    result = simulate_session(personas["P3"], "S2", iteration=0, max_turns=4)
    assert result.transcript[0]["role"] == "customer"
    assert any(t["role"] == "advisor" for t in result.transcript)
    assert 1 <= result.verdict.turns_to_decision <= 4
    assert 1 <= result.verdict.trust_score <= 5
    assert result.trust_history[0] == pytest.approx(TRUST_START, abs=0.5)
    # S2 는 인용 정책상 소유 자산을 근거로 써야 한다.
    assert result.owned_assets_used is True
    assert result.cited_asset_ids


def test_s1_session_has_no_citation(personas):
    result = simulate_session(personas["P3"], "S1", iteration=0, max_turns=3)
    assert result.owned_assets_used is False
    assert result.cited_asset_ids == []


def test_lab_config_totals():
    config = LabConfig.from_settings(runs_per_pair=2)
    assert config.total_sessions == len(config.persona_ids) * len(config.strategy_ids) * 2


def test_summarize_empty_run_is_safe():
    data = summarize("run-does-not-exist")
    assert data["totals"]["sessions"] == 0
    assert all(row["sessions"] == 0 for row in data["by_strategy"])
    assert data["simulation_mode"]["caveat"]
