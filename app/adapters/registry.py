"""어댑터 레지스트리 — env 로 모듈별 mock/http 를 고른다.

    ADAPTER_MODE=mock|http                 전역 기본값
    INTENT_ADAPTER / CLIENTELING_ADAPTER / ASSET_ADAPTER /
    FINGERPRINT_ADAPTER / CONDITION_ADAPTER = mock|http    모듈별 오버라이드(전역보다 우선)

팀원 모듈이 하나씩 완성되므로 부분 전환이 필수다. 예: 인텐트만 실서버로

    INTENT_ADAPTER=http make dev

인스턴스는 모듈별 싱글턴이다. `AdapterStatus` 가 누적돼야 `/health/detail` 에서 최근 호출 결과를
볼 수 있기 때문이다.
"""

from __future__ import annotations

from typing import Any

from app.adapters.assets import HttpAssetAdapter, MockAssetAdapter
from app.adapters.base import AssetPort, ClientelingPort, ConditionPort, FingerprintPort, IntentPort
from app.adapters.clienteling import HttpClientelingAdapter, MockClientelingAdapter
from app.adapters.condition import HttpConditionAdapter, MockConditionAdapter
from app.adapters.fingerprint import HttpFingerprintAdapter, MockFingerprintAdapter
from app.adapters.intent import HttpIntentAdapter, MockIntentAdapter
from app.config import MODULE_KEYS, ModuleKey, get_settings

_cache: dict[str, Any] = {}


def _resolve(module: ModuleKey, mock_cls: type[Any], http_cls: type[Any]) -> Any:
    mode = get_settings().module_mode(module)
    key = f"{module}:{mode}"
    if key not in _cache:
        _cache[key] = http_cls() if mode == "http" else mock_cls()
    return _cache[key]


def get_intent_adapter() -> IntentPort:
    adapter: IntentPort = _resolve("intent", MockIntentAdapter, HttpIntentAdapter)
    return adapter


def get_clienteling_adapter() -> ClientelingPort:
    adapter: ClientelingPort = _resolve(
        "clienteling", MockClientelingAdapter, HttpClientelingAdapter
    )
    return adapter


def get_asset_adapter() -> AssetPort:
    adapter: AssetPort = _resolve("asset", MockAssetAdapter, HttpAssetAdapter)
    return adapter


def get_fingerprint_adapter() -> FingerprintPort:
    adapter: FingerprintPort = _resolve(
        "fingerprint", MockFingerprintAdapter, HttpFingerprintAdapter
    )
    return adapter


def get_condition_adapter() -> ConditionPort:
    adapter: ConditionPort = _resolve("condition", MockConditionAdapter, HttpConditionAdapter)
    return adapter


_GETTERS = {
    "intent": get_intent_adapter,
    "clienteling": get_clienteling_adapter,
    "asset": get_asset_adapter,
    "fingerprint": get_fingerprint_adapter,
    "condition": get_condition_adapter,
}


def all_adapters() -> dict[str, Any]:
    """모듈 → 어댑터 인스턴스. 헬스 대시보드가 쓴다."""
    return {module: _GETTERS[module]() for module in MODULE_KEYS}


def adapter_report() -> list[dict[str, Any]]:
    """어댑터별 모드·최근 상태 요약."""
    settings = get_settings()
    out: list[dict[str, Any]] = []
    for module, adapter in all_adapters().items():
        info = adapter.status.as_dict()
        info["override"] = getattr(settings, f"{module}_adapter") is not None
        out.append(info)
    return out


def reset_adapters() -> None:
    """테스트/전환 확인용. env 를 바꾼 뒤 인스턴스를 새로 만든다."""
    _cache.clear()
