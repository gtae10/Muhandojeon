"""데모 시나리오 — `data/demo_scenarios.yaml` 로딩과 실행.

시나리오는 고객·상품·전략·세션을 **픽스처 id 로 못박은** 고정 입력이다(무작위 선택 금지 →
매번 같은 흐름). 세션 이벤트는 `fixtures/session_events.json` 의 시나리오를 provider 경유로 읽는다.

`expect` 블록은 `scripts/check_demo.py` 가 검증한다. 발표 직전에 이 검증이 통과해야 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import DATA_DIR
from app.store import DataStore, SessionRecord, get_store
from contracts.common import SessionEvent
from contracts.orchestrator import AdviseRequest

SCENARIOS_PATH = DATA_DIR / "demo_scenarios.yaml"


@dataclass(frozen=True)
class Scenario:
    """데모 시나리오 1건."""

    id: str
    title: str
    narrative: str
    customer_id: str
    target_product_id: str
    session_id: str
    strategy_id: str
    talking_points: tuple[str, ...]
    expect: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "narrative": self.narrative.strip(),
            "customer_id": self.customer_id,
            "target_product_id": self.target_product_id,
            "session_id": self.session_id,
            "strategy_id": self.strategy_id,
            "talking_points": list(self.talking_points),
            "expect": self.expect,
        }


def _parse(raw: dict[str, Any]) -> Scenario:
    return Scenario(
        id=str(raw["id"]),
        title=str(raw.get("title", raw["id"])),
        narrative=str(raw.get("narrative", "")),
        customer_id=str(raw["customer_id"]),
        target_product_id=str(raw["target_product_id"]),
        session_id=str(raw["session_id"]),
        strategy_id=str(raw.get("strategy_id", "S2")),
        talking_points=tuple(str(t) for t in raw.get("talking_points", [])),
        expect=dict(raw.get("expect", {})),
    )


@lru_cache(maxsize=1)
def load_scenarios(path: Path | None = None) -> dict[str, Scenario]:
    """시나리오 사전. 파일이 없으면 빈 사전(헬스 대시보드가 0으로 표시한다)."""
    target = path or SCENARIOS_PATH
    if not target.exists():
        return {}
    loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return {s.id: s for s in (_parse(item) for item in loaded.get("scenarios", []))}


def pick_session(scenario: Scenario, store: DataStore | None = None) -> SessionRecord | None:
    """시나리오가 지정한 픽스처 세션. id 로 고정돼 있어 매 실행 동일하다."""
    target = store or get_store()
    return target.sessions.get(scenario.session_id)


def build_request(scenario: Scenario, store: DataStore | None = None) -> AdviseRequest:
    """시나리오를 `/session/advise` 요청으로 만든다."""
    session = pick_session(scenario, store)
    events: list[SessionEvent] = list(session.events) if session else []
    return AdviseRequest(
        customer_id=scenario.customer_id,
        target_product_id=scenario.target_product_id,
        session_events=events,
        strategy_id=scenario.strategy_id,
        history=[],
        scenario_id=scenario.id,
    )


def check_expectations(scenario: Scenario, response: Any) -> list[str]:
    """`expect` 블록 검증. 위반 목록을 반환한다(빈 목록이면 통과)."""
    problems: list[str] = []
    expect = scenario.expect
    if not expect:
        return problems

    wanted = expect.get("hesitation_type")
    if wanted and response.hesitation_type.value != wanted:
        problems.append(f"망설임 유형 {response.hesitation_type.value} ≠ 기대 {wanted}")

    if expect.get("owned_assets_used") is True and not response.owned_assets_used:
        problems.append("소유 자산 인용 없음 (owned_assets_used=false)")

    min_citations = int(expect.get("min_citations", 0))
    if len(response.cited_asset_ids) < min_citations:
        problems.append(f"인용 {len(response.cited_asset_ids)}건 < 최소 {min_citations}건")

    cta_in = expect.get("cta_in")
    if cta_in and response.cta.value not in cta_in:
        problems.append(f"CTA {response.cta.value} 가 허용 목록 {cta_in} 밖")

    condition = expect.get("must_include_asset_condition")
    if condition is not None:
        scores = [c.condition_score for c in response.citations]
        if int(condition) not in scores:
            problems.append(f"컨디션 {condition}점 개체가 인용되지 않았다 (인용된 점수 {scores})")

    if response.degraded:
        problems.append("degraded=true — 업스트림 폴백이 발생했다")
    return problems
