"""상담 전략 로딩 — `data/strategies.yaml`.

전략은 상담 어댑터(LLM 프롬프트 + 결정적 템플릿)와 Persona Bot Lab 이 함께 쓴다.
`cite_assets` 가 전략 간 핵심 차이이고, 그 차이가 Lab 의 측정 대상이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import DATA_DIR
from contracts.common import CTA

STRATEGIES_PATH = DATA_DIR / "strategies.yaml"


@dataclass(frozen=True)
class Strategy:
    """상담 전략 1종."""

    id: str
    name: str
    summary: str
    tone: str
    cite_assets: bool
    max_citations: int
    scarcity_pressure: float
    cta_preference: CTA
    instructions: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "cite_assets": self.cite_assets,
            "max_citations": self.max_citations,
            "scarcity_pressure": self.scarcity_pressure,
            "cta_preference": self.cta_preference.value,
        }


DEFAULT_STRATEGY = Strategy(
    id="S2",
    name="소유 자산 연계형",
    summary="고객이 실제 소유한 개체와 컨디션을 근거로 제안한다",
    tone="근거를 먼저 대고 제안하는 어조",
    cite_assets=True,
    max_citations=2,
    scarcity_pressure=0.0,
    cta_preference=CTA.BOOK_FITTING,
    instructions="소유 개체의 구매 연도·컨디션 점수·소견을 인용한다.",
)


def _parse(raw: dict[str, Any]) -> Strategy:
    return Strategy(
        id=str(raw["id"]),
        name=str(raw.get("name", raw["id"])),
        summary=str(raw.get("summary", "")),
        tone=str(raw.get("tone", "")),
        cite_assets=bool(raw.get("cite_assets", False)),
        max_citations=int(raw.get("max_citations", 0)),
        scarcity_pressure=float(raw.get("scarcity_pressure", 0.0)),
        cta_preference=CTA(str(raw.get("cta_preference", CTA.NONE.value))),
        instructions=str(raw.get("instructions", "")).strip(),
    )


@lru_cache(maxsize=1)
def load_strategies(path: Path | None = None) -> dict[str, Strategy]:
    """전략 사전. 파일이 없으면 기본 전략(S2) 하나로 동작한다(크래시 금지)."""
    target = path or STRATEGIES_PATH
    if not target.exists():
        return {DEFAULT_STRATEGY.id: DEFAULT_STRATEGY}
    loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    items = loaded.get("strategies", [])
    out = {s.id: s for s in (_parse(item) for item in items)}
    return out or {DEFAULT_STRATEGY.id: DEFAULT_STRATEGY}


def get_strategy(strategy_id: str) -> Strategy:
    """id 로 전략을 찾는다. 없으면 S2(또는 첫 전략)로 폴백."""
    strategies = load_strategies()
    if strategy_id in strategies:
        return strategies[strategy_id]
    return strategies.get("S2") or next(iter(strategies.values()))
