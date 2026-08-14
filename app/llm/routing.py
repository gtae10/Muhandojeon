"""모델 라우팅 — 용도 → 티어 → 실제 모델명.

`config/model_routing.yaml` 이 정책이고 코드는 그 정책을 읽을 뿐이다. 모델명은
`/models` 조회로 채우되 **1회만 호출하고 결과를 디스크에 캐시**한다(조회도 크레딧을 쓴다).
조회가 실패하면 env → fallback 순으로 내려간다.

능력 플래그(`config/llm_capabilities.json`)도 여기서 읽는다. **런타임 탐지는 하지 않는다** —
비전 부재가 확정됐으므로 파일 값을 신뢰한다.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

import httpx
import yaml

from app.config import CONFIG_DIR, get_settings

logger = logging.getLogger("app.llm.routing")

ROUTING_PATH = CONFIG_DIR / "model_routing.yaml"
CAPABILITIES_PATH = CONFIG_DIR / "llm_capabilities.json"

Purpose = Literal["clienteling", "judge", "persona", "intent", "condition_note", "other"]
PURPOSES: tuple[Purpose, ...] = (
    "clienteling",
    "judge",
    "persona",
    "intent",
    "condition_note",
    "other",
)
Tier = Literal["high", "low"]


@dataclass(frozen=True)
class Route:
    """한 용도의 라우팅 결과."""

    purpose: str
    tier: Tier
    model: str
    reason: str
    source: str  # discovery | env | fallback


@lru_cache(maxsize=1)
def load_routing() -> dict[str, Any]:
    if not ROUTING_PATH.exists():
        logger.warning("라우팅 파일이 없다: %s → 전부 상위 티어로 간다", ROUTING_PATH)
        return {}
    loaded = yaml.safe_load(ROUTING_PATH.read_text(encoding="utf-8")) or {}
    return loaded if isinstance(loaded, dict) else {}


@lru_cache(maxsize=1)
def load_capabilities() -> dict[str, bool]:
    """능력 플래그. 파일이 없으면 보수적으로 전부 false 로 본다(특히 vision)."""
    if not CAPABILITIES_PATH.exists():
        logger.warning("능력 플래그 파일이 없다: %s → vision=false 로 간주", CAPABILITIES_PATH)
        return {"vision": False, "embeddings": False}
    loaded = json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))
    caps = loaded.get("capabilities", {})
    return {str(k): bool(v) for k, v in caps.items()}


def supports_vision() -> bool:
    """비전 입력 가능 여부. **확정: false** — 이미지 경로를 만들면 안 된다."""
    return load_capabilities().get("vision", False)


def tier_for(purpose: str) -> tuple[Tier, str]:
    purposes = load_routing().get("purposes") or {}
    entry = purposes.get(purpose) or purposes.get("other") or {}
    tier = str(entry.get("tier", "high"))
    reason = str(entry.get("reason", ""))
    return ("low" if tier == "low" else "high"), reason


@lru_cache(maxsize=1)
def discovered_models() -> list[str]:
    """`/models` 를 1회 조회해 디스크에 캐시한다. 실패하면 빈 목록."""
    settings = get_settings()
    routing = load_routing().get("discovery") or {}
    if not settings.llm_models_discovery or not routing.get("enabled", True):
        return []
    if not settings.llm_enabled or settings.llm_dry_run:
        return []

    cache_path = settings.llm_cache_dir / str(routing.get("cache_file", "models.json"))
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            models = [str(m) for m in cached.get("models", [])]
            if models:
                return models
        except (json.JSONDecodeError, OSError):
            pass

    url = f"{settings.llm_base_url.rstrip('/')}{routing.get('endpoint', '/models')}"
    try:
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.upstream_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("모델 목록 조회 실패(%s) → env/fallback 사용: %s", url, exc)
        return []

    items = payload.get("data") if isinstance(payload, dict) else payload
    models = [
        str(item.get("id")) for item in (items or []) if isinstance(item, dict) and item.get("id")
    ]
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"models": models}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:  # pragma: no cover
        pass
    logger.info("모델 목록 %d개 조회 완료 (캐시: %s)", len(models), cache_path)
    return models


def resolve(purpose: str) -> Route:
    """용도에 쓸 모델을 결정한다. discovery → env → fallback."""
    settings = get_settings()
    tier, reason = tier_for(purpose)
    routing = load_routing()
    tier_conf = (routing.get("tiers") or {}).get(tier) or {}

    available = discovered_models()
    if available:
        prefer = ((routing.get("discovery") or {}).get("prefer") or {}).get(tier) or []
        for candidate in prefer:
            for model_id in available:
                if candidate.lower() in model_id.lower():
                    return Route(purpose, tier, model_id, reason, "discovery")

    env_name = str(tier_conf.get("model_env", ""))
    env_value = os.environ.get(env_name, "").strip() if env_name else ""
    if env_value:
        return Route(purpose, tier, env_value, reason, "env")

    # env 미설정 → Settings 기본값(상위=llm_model, 저가=cheap_model)
    settings_value = settings.cheap_model if tier == "low" else settings.llm_model
    if settings_value:
        return Route(purpose, tier, settings_value, reason, "env")

    return Route(purpose, tier, str(tier_conf.get("fallback", "gpt-4o-mini")), reason, "fallback")


def routing_report() -> list[dict[str, Any]]:
    """용도별 라우팅 요약. `/ops` 와 `/health/detail` 이 쓴다."""
    out: list[dict[str, Any]] = []
    for purpose in PURPOSES:
        route = resolve(purpose)
        from app.llm.pricing import price_for

        price = price_for(route.model)
        out.append(
            {
                "purpose": purpose,
                "tier": route.tier,
                "model": route.model,
                "source": route.source,
                "reason": route.reason,
                "input_per_1m_usd": price.input_per_1m,
                "output_per_1m_usd": price.output_per_1m,
                "pricing_entry": price.source,
            }
        )
    return out


def reset_routing_cache() -> None:
    """테스트/설정 변경 후 캐시 초기화."""
    load_routing.cache_clear()
    load_capabilities.cache_clear()
    discovered_models.cache_clear()
