"""페르소나 로딩 — `data/personas.yaml`.

페르소나는 **실제 고객(CU-xxxx)에 바인딩**된다. 소유 자산이 있는 실제 고객이어야 전략 S2
(소유 자산 연계형)를 검증할 수 있기 때문이다. 바인딩이 깨졌으면(고객이 사라졌거나 자산이 없거나)
`validate_bindings()` 가 알려준다.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import DATA_DIR
from app.store import DataStore, get_store
from contracts.common import HesitationType

PERSONAS_PATH = DATA_DIR / "personas.yaml"

#: needs 키 → 사람이 읽는 설명. 판정 규칙과 프롬프트가 공유한다.
NEED_LABELS: dict[str, str] = {
    "style_fit": "취향·스타일 적합성",
    "size_fit": "사이즈·핏 확신",
    "price_value": "가격 대비 가치",
    "care_cost": "관리 비용과 수명",
    "resale_value": "자산 가치 유지",
    "stock_certainty": "재고·입고 확실성",
    "relationship": "내 기록을 알고 있다는 확인",
}


@dataclass(frozen=True)
class Persona:
    """고객 봇 1종."""

    id: str
    name: str
    customer_id: str
    target_product_id: str
    binding_note: str
    initial_hesitation: HesitationType
    goal: str
    budget_sensitivity: float
    evidence_need: float
    pressure_aversion: float
    brand_familiarity: float
    trust_threshold: float
    patience_turns: int
    needs: tuple[str, ...]
    tone: str
    openings: tuple[str, ...]

    def opening(self, iteration: int) -> str:
        """반복 회차별 오프닝. 결정적 시스템에서 같은 조건 3회는 의미가 없으므로 변형을 준다."""
        if not self.openings:
            return "상담 부탁드립니다."
        return self.openings[iteration % len(self.openings)]

    @property
    def need_labels(self) -> list[str]:
        return [NEED_LABELS.get(n, n) for n in self.needs]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "customer_id": self.customer_id,
            "target_product_id": self.target_product_id,
            "initial_hesitation": self.initial_hesitation.value,
            "needs": list(self.needs),
            "trust_threshold": self.trust_threshold,
            "patience_turns": self.patience_turns,
            "binding_note": self.binding_note,
        }


def _parse(raw: dict[str, Any]) -> Persona:
    return Persona(
        id=str(raw["id"]),
        name=str(raw.get("name", raw["id"])),
        customer_id=str(raw["customer_id"]),
        target_product_id=str(raw["target_product_id"]),
        binding_note=str(raw.get("binding_note", "")),
        initial_hesitation=HesitationType(str(raw.get("initial_hesitation", "NONE"))),
        goal=str(raw.get("goal", "")),
        budget_sensitivity=float(raw.get("budget_sensitivity", 0.5)),
        evidence_need=float(raw.get("evidence_need", 0.5)),
        pressure_aversion=float(raw.get("pressure_aversion", 0.5)),
        brand_familiarity=float(raw.get("brand_familiarity", 0.5)),
        trust_threshold=float(raw.get("trust_threshold", 3.7)),
        patience_turns=int(raw.get("patience_turns", 6)),
        needs=tuple(str(n) for n in raw.get("needs", [])),
        tone=str(raw.get("tone", "")),
        openings=tuple(str(o) for o in raw.get("openings", [])),
    )


@lru_cache(maxsize=1)
def load_personas(path: Path | None = None) -> dict[str, Persona]:
    """페르소나 사전. 파일이 없으면 빈 사전(Lab 이 그 사실을 보고한다)."""
    target = path or PERSONAS_PATH
    if not target.exists():
        return {}
    loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return {p.id: p for p in (_parse(item) for item in loaded.get("personas", []))}


def validate_bindings(store: DataStore | None = None) -> list[str]:
    """바인딩 무결성 검사. 문제 목록을 반환한다(빈 목록이면 정상)."""
    target = store or get_store()
    problems: list[str] = []
    for persona in load_personas().values():
        customer = target.customer(persona.customer_id)
        if customer is None:
            problems.append(f"{persona.id}: 고객 {persona.customer_id} 없음")
            continue
        if not customer.assets:
            problems.append(f"{persona.id}: 고객 {persona.customer_id} 에 소유 개체가 없음")
        if target.product(persona.target_product_id) is None:
            problems.append(f"{persona.id}: 상품 {persona.target_product_id} 없음")
    return problems
