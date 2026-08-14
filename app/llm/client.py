"""OpenAI 호환 LLM 클라이언트 — 로컬 vLLM과 상용 API 양쪽에 붙는 단일 진입점.

특정 벤더 SDK를 import 하지 않고 `/chat/completions` 만 httpx 로 호출한다.
`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` 로 전환한다.

**크레딧 100달러가 총액이고 초과 시 복구 수단이 없다.** 그래서 모든 호출은 이 게이트웨이를
지나며 다음 순서로 처리된다.

    1. 라우팅   — 용도(purpose)로 티어/모델 결정 (config/model_routing.yaml)
    2. 캐시     — 기본 활성화. 프롬프트+모델+temperature+seed 해시로 조회
    3. 드라이런 — LLM_DRY_RUN=true 면 호출 없이 토큰·비용만 추정해 기록
    4. 예산     — 호출 **전에** 예상 비용을 더해 하드 리밋을 넘기면 거부(캐시 폴백)
    5. 호출     — 성공 시 응답의 usage 로 실측 기록, 실패 시 결정적 폴백
    6. 기록     — llm_usage 테이블에 용도·모델·토큰·비용·지연·캐시히트 기록

비전 입력은 지원하지 않는다(`config/llm_capabilities.json` 의 vision=false 확정).
이미지를 프롬프트에 넣는 경로를 만들지 않는다 — 호출이 실패하면서 토큰만 소모한다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TypedDict

import httpx

from app.config import Settings, get_settings
from app.llm.budget import BudgetExceeded, get_budget
from app.llm.pricing import estimate_prompt_tokens, estimate_tokens, price_for
from app.llm.routing import resolve

logger = logging.getLogger("app.llm")


class Message(TypedDict):
    """OpenAI 호환 chat 메시지 (텍스트 전용)."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMStats:
    """프로세스 내 호출 통계. `/health/detail` 에 그대로 노출된다."""

    calls: int = 0
    cache_hits: int = 0
    cache_writes: int = 0
    fallbacks: int = 0
    refusals: int = 0
    dry_runs: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "cache_writes": self.cache_writes,
            "fallbacks": self.fallbacks,
            "refusals": self.refusals,
            "dry_runs": self.dry_runs,
            "last_error": self.errors[-1] if self.errors else None,
        }


class LLMClient:
    """OpenAI 호환 chat completion 래퍼 + 예산 게이트."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.stats = LLMStats()
        self._cache_dir = self.settings.llm_cache_dir

    # ── 캐시 ──────────────────────────────────────────────────
    def cache_key(self, messages: Sequence[Message], model: str, temperature: float) -> str:
        """프롬프트 해시 + 모델 + temperature + seed.

        모델명을 키에 넣기 때문에 티어를 바꾸면 캐시가 자동으로 무효화된다.
        프롬프트에 현재 시각·UUID 같은 비결정적 값이 섞이면 이 키가 매번 달라져 캐시가 죽는다
        (그래서 픽스처 타임스탬프를 고정값으로 두고 `scripts/cache_stats.py` 로 히트율을 본다).
        """
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
        return len([p for p in self._cache_dir.glob("*.json") if p.name != "models.json"])

    def _cache_read(self, key: str) -> dict[str, Any] | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) and isinstance(data.get("text"), str) else None

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
        purpose: str = "other",
        fallback: Callable[[], str] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        cache: bool | None = None,
        run_id: str | None = None,
    ) -> str:
        """chat completion 1회. 실패·거부·미연결 모두 fallback() 으로 흡수한다(예외 없음)."""
        route = resolve(purpose)
        model = model or route.model
        temperature = self.settings.llm_temperature if temperature is None else temperature
        limit = max_tokens or self.settings.llm_max_tokens
        use_cache = self.settings.llm_cache_enabled if cache is None else cache
        key = self.cache_key(messages, model, temperature)
        budget = get_budget()
        prompt_tokens, out_limit, projected = self._estimate(messages, model, limit)

        def record(**kwargs: Any) -> None:
            budget.record(
                purpose=purpose,
                tier=route.tier,
                model=model or "",
                cache_key=key,
                run_id=run_id,
                **kwargs,
            )

        # 1) 캐시
        if use_cache:
            cached = self._cache_read(key)
            if cached is not None:
                self.stats.cache_hits += 1
                text = str(cached["text"])
                record(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=estimate_tokens(text),
                    estimated=True,
                    cached=True,
                    dry_run=False,
                    latency_ms=0.0,
                    note="cache-hit",
                )
                return text

        # 2) 드라이런 — 호출하지 않고 비용만 추정
        if self.settings.llm_dry_run:
            self.stats.dry_runs += 1
            text = fallback() if fallback else ""
            record(
                prompt_tokens=prompt_tokens,
                completion_tokens=out_limit,
                estimated=True,
                cached=False,
                dry_run=True,
                latency_ms=0.0,
                note=f"dry-run est ${projected:.4f}",
            )
            return text

        # 3) 키 없음 — 결정적 템플릿 폴백
        if not self.settings.llm_enabled:
            self.stats.fallbacks += 1
            text = fallback() if fallback else ""
            record(
                prompt_tokens=prompt_tokens,
                completion_tokens=estimate_tokens(text),
                estimated=True,
                cached=False,
                dry_run=True,
                latency_ms=0.0,
                note="no-api-key (template fallback)",
            )
            return text

        # 4) 예산 게이트 (사후 집계로는 늦다)
        try:
            budget.check_before_call(purpose, model, projected, settings=self.settings)
        except BudgetExceeded as exc:
            self.stats.refusals += 1
            logger.error("호출 거부: %s", exc)
            text = fallback() if fallback else ""
            record(
                prompt_tokens=0,
                completion_tokens=0,
                estimated=True,
                cached=False,
                dry_run=True,
                latency_ms=0.0,
                note="refused: budget hard limit",
            )
            return text

        # 5) 실제 호출
        body: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": limit,
            "seed": self.settings.llm_seed,
        }
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        url = f"{self.settings.llm_base_url.rstrip('/')}/chat/completions"

        last_error = ""
        started = time.perf_counter()
        for attempt in range(1 + self.settings.upstream_retries):
            try:
                resp = httpx.post(
                    url, json=body, headers=headers, timeout=self.settings.llm_timeout_seconds
                )
                resp.raise_for_status()
                data = resp.json()
                text = str(data["choices"][0]["message"]["content"]).strip()
                elapsed = (time.perf_counter() - started) * 1000
                usage = data.get("usage") or {}
                actual_prompt = int(usage.get("prompt_tokens") or 0)
                actual_completion = int(usage.get("completion_tokens") or 0)
                estimated = not (actual_prompt or actual_completion)
                self.stats.calls += 1
                cost = 0.0
                record(
                    prompt_tokens=actual_prompt or prompt_tokens,
                    completion_tokens=actual_completion or estimate_tokens(text),
                    estimated=estimated,
                    cached=False,
                    dry_run=False,
                    latency_ms=elapsed,
                    note=f"pricing={price_for(model).source}",
                )
                if use_cache:
                    self._cache_write(
                        key,
                        text,
                        {
                            "source": "api",
                            "model": model,
                            "purpose": purpose,
                            "tier": route.tier,
                            "cost_usd_estimate": round(cost, 6),
                        },
                    )
                return text
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("LLM 호출 실패(%d회차): %s", attempt + 1, last_error)

        # 6) 실패 — 폴백. 실패한 호출은 청구되지 않는다고 보고 비청구로 기록한다.
        self.stats.errors.append(last_error)
        self.stats.fallbacks += 1
        text = fallback() if fallback else ""
        record(
            prompt_tokens=0,
            completion_tokens=0,
            estimated=True,
            cached=False,
            dry_run=True,
            latency_ms=(time.perf_counter() - started) * 1000,
            note=f"error: {last_error}"[:200],
        )
        return text

    def _estimate(
        self, messages: Sequence[Message], model: str, max_tokens: int
    ) -> tuple[int, int, float]:
        prompt_tokens = estimate_prompt_tokens([dict(m) for m in messages])
        price = price_for(model)
        return prompt_tokens, max_tokens, price.cost_usd(prompt_tokens, max_tokens)

    def complete_json(
        self,
        messages: Sequence[Message],
        *,
        fallback: Callable[[], Any],
        purpose: str = "other",
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        cache: bool | None = None,
        run_id: str | None = None,
    ) -> Any:
        """JSON 응답을 기대하는 호출. 파싱 실패도 폴백으로 흡수한다."""
        raw = self.complete(
            messages,
            purpose=purpose,
            fallback=lambda: json.dumps(fallback(), ensure_ascii=False),
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            cache=cache,
            run_id=run_id,
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
