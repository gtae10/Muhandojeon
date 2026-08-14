"""OpenAI 호환 LLM 클라이언트 — 로컬 vLLM과 상용 API 양쪽에 붙는 단일 진입점.

특정 벤더 SDK를 import 하지 않고 `/chat/completions` 만 httpx 로 호출한다.
`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` 로 전환한다.

세 가지 안전장치가 데모를 지킨다.
1. **디스크 캐시** — `DEMO_MODE=true` 또는 `cache=True` 면 동일 입력을 `.cache/llm/` 에서 반환한다.
   네트워크가 끊겨도 워밍업된 시나리오는 그대로 돌아간다.
2. **결정적 폴백** — 키가 없거나 호출이 실패하면 호출자가 준 `fallback()` 문자열을 쓴다.
   예외를 밖으로 던지지 않는다.
3. **통계** — 호출/캐시히트/폴백 건수를 남겨 `/health/detail` 에서 확인한다.

기본 temperature 는 0, seed 는 고정이다. 데모 재현성이 창의성보다 우선한다.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger("app.llm")


class Message(TypedDict):
    """OpenAI 호환 chat 메시지."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMStats:
    """호출 통계. `/health/detail` 에 그대로 노출된다."""

    calls: int = 0
    cache_hits: int = 0
    cache_writes: int = 0
    fallbacks: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "cache_writes": self.cache_writes,
            "fallbacks": self.fallbacks,
            "last_error": self.errors[-1] if self.errors else None,
        }


class LLMClient:
    """OpenAI 호환 chat completion 래퍼."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.stats = LLMStats()
        self._cache_dir = self.settings.llm_cache_dir

    # ── 캐시 ──────────────────────────────────────────────────
    def cache_key(self, messages: Sequence[Message], model: str, temperature: float) -> str:
        payload = json.dumps(
            {"m": list(messages), "model": model, "t": temperature, "s": self.settings.llm_seed},
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]

    def _cache_path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def cache_count(self) -> int:
        if not self._cache_dir.exists():
            return 0
        return len(list(self._cache_dir.glob("*.json")))

    def _cache_read(self, key: str) -> str | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        text = data.get("text")
        return text if isinstance(text, str) else None

    def _cache_write(self, key: str, text: str, meta: dict[str, Any]) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._cache_path(key).write_text(
                json.dumps({"text": text, **meta}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.stats.cache_writes += 1
        except OSError as exc:  # pragma: no cover
            logger.warning("LLM 캐시 쓰기 실패: %s", exc)

    # ── 호출 ──────────────────────────────────────────────────
    def complete(
        self,
        messages: Sequence[Message],
        *,
        fallback: Callable[[], str] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        cache: bool | None = None,
    ) -> str:
        """chat completion 1회. 실패 시 fallback() 을 반환하며 예외를 던지지 않는다."""
        model = model or self.settings.llm_model
        temperature = self.settings.llm_temperature if temperature is None else temperature
        use_cache = self.settings.demo_mode if cache is None else cache
        key = self.cache_key(messages, model, temperature)

        if use_cache:
            cached = self._cache_read(key)
            if cached is not None:
                self.stats.cache_hits += 1
                return cached

        if not self.settings.llm_enabled:
            self.stats.fallbacks += 1
            logger.debug("LLM_API_KEY 없음 → 결정적 폴백 사용")
            text = fallback() if fallback else ""
            if use_cache and text:
                self._cache_write(key, text, {"source": "fallback", "model": model})
            return text

        body: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens or self.settings.llm_max_tokens,
            "seed": self.settings.llm_seed,
        }
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"

        last_error = ""
        for attempt in range(1 + self.settings.upstream_retries):
            try:
                resp = httpx.post(
                    url, json=body, headers=headers, timeout=self.settings.llm_timeout_seconds
                )
                resp.raise_for_status()
                data = resp.json()
                text = str(data["choices"][0]["message"]["content"]).strip()
                self.stats.calls += 1
                if use_cache:
                    self._cache_write(key, text, {"source": "api", "model": model})
                return text
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("LLM 호출 실패(%d회차): %s", attempt + 1, last_error)

        self.stats.errors.append(last_error)
        self.stats.fallbacks += 1
        text = fallback() if fallback else ""
        if use_cache and text:
            self._cache_write(key, text, {"source": "fallback-after-error", "model": model})
        return text

    def complete_json(
        self,
        messages: Sequence[Message],
        *,
        fallback: Callable[[], Any],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        cache: bool | None = None,
    ) -> Any:
        """JSON 응답을 기대하는 호출. 파싱 실패도 폴백으로 흡수한다."""
        raw = self.complete(
            messages,
            fallback=lambda: json.dumps(fallback(), ensure_ascii=False),
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            cache=cache,
        )
        parsed = extract_json(raw)
        if parsed is None:
            logger.warning("LLM JSON 파싱 실패 → 폴백 (앞 120자: %s)", raw[:120])
            self.stats.fallbacks += 1
            return fallback()
        return parsed


def extract_json(text: str) -> Any | None:
    """LLM 출력에서 JSON 객체/배열을 최대한 관대하게 뽑아낸다."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = [ln for ln in cleaned.splitlines() if not ln.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    """프로세스 전역 LLM 클라이언트."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
