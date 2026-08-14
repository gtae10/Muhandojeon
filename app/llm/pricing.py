"""토큰 추정과 단가 계산.

예산 가드가 **호출 전에** 비용을 알아야 하므로 토큰을 추정한다. 응답에 `usage` 가 오면 그
실측값으로 기록을 덮어쓴다(추정은 게이트용, 기록은 실측 우선).

토큰 추정은 tiktoken 없이 문자 기반 근사다. 한국어는 영문보다 토큰이 촘촘하므로 ASCII 와
비ASCII 를 나눠 계산한다. tiktoken 이 설치돼 있으면 그걸 우선 쓴다.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml

from app.config import CONFIG_DIR

logger = logging.getLogger("app.llm.pricing")

PRICING_PATH = CONFIG_DIR / "model_pricing.yaml"

#: ASCII 문자당 토큰 (영문/숫자/기호 ≈ 4자 1토큰)
_ASCII_CHARS_PER_TOKEN = 4.0
#: 비ASCII 문자당 토큰 (한글은 대략 1.3자 1토큰)
_CJK_CHARS_PER_TOKEN = 1.3
#: 메시지당 오버헤드(role, 구분자)
_MESSAGE_OVERHEAD_TOKENS = 4


@dataclass(frozen=True)
class Price:
    """모델 단가."""

    model: str
    input_per_1m: float
    output_per_1m: float
    source: str  # matched model key | default

    def cost_usd(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (
            prompt_tokens * self.input_per_1m + completion_tokens * self.output_per_1m
        ) / 1_000_000


@lru_cache(maxsize=1)
def _load_pricing() -> dict[str, Any]:
    if not PRICING_PATH.exists():
        logger.warning("단가 파일이 없다: %s → 기본 단가로 계산한다", PRICING_PATH)
        return {"default": {"input_per_1m": 1.0, "output_per_1m": 3.0}, "models": {}}
    loaded = yaml.safe_load(PRICING_PATH.read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


def price_for(model: str) -> Price:
    """모델 단가. 정확히 일치 → 부분 일치 → default 순으로 찾는다."""
    data = _load_pricing()
    models: dict[str, Any] = data.get("models") or {}
    key = model.strip()
    if key in models:
        entry = models[key]
        return Price(model, float(entry["input_per_1m"]), float(entry["output_per_1m"]), key)
    lowered = key.lower()
    for name, entry in models.items():
        if name.lower() in lowered:
            return Price(model, float(entry["input_per_1m"]), float(entry["output_per_1m"]), name)
    fallback = data.get("default") or {}
    return Price(
        model,
        float(fallback.get("input_per_1m", 1.0)),
        float(fallback.get("output_per_1m", 3.0)),
        "default",
    )


def estimate_tokens(text: str) -> int:
    """문자열의 토큰 수 추정. tiktoken 이 있으면 실측에 가깝게 센다."""
    if not text:
        return 0
    try:  # pragma: no cover - 설치 여부에 따라 갈린다
        import tiktoken

        return len(tiktoken.get_encoding("cl100k_base").encode(text))
    except Exception:  # noqa: BLE001 - 없으면 근사식으로 간다
        ascii_chars = sum(1 for ch in text if ord(ch) < 128)
        cjk_chars = len(text) - ascii_chars
        return int(ascii_chars / _ASCII_CHARS_PER_TOKEN + cjk_chars / _CJK_CHARS_PER_TOKEN) + 1


def estimate_prompt_tokens(messages: Sequence[dict[str, Any]]) -> int:
    """메시지 배열의 입력 토큰 추정."""
    total = 0
    for message in messages:
        total += estimate_tokens(str(message.get("content", "")))
        total += _MESSAGE_OVERHEAD_TOKENS
    return total


def estimate_call_cost(
    model: str, messages: Sequence[dict[str, Any]], max_tokens: int
) -> tuple[int, int, float]:
    """(입력 토큰, 출력 토큰 상한, 예상 최대 비용). 게이트는 최악의 경우로 판단한다."""
    prompt = estimate_prompt_tokens(messages)
    price = price_for(model)
    return prompt, max_tokens, price.cost_usd(prompt, max_tokens)
