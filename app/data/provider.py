"""시드 데이터 provider — **데이터 접근의 유일한 경계**.

외부 데이터셋이 확정되지 않았으므로 지금은 손으로 쓴 `fixtures/*.json` 을 쓴다. 데이터셋이
정해지면 `DatasetProvider` 만 채우고 `SEED_SOURCE=dataset` 으로 전환한다 — 오케스트레이터와
목 어댑터는 손대지 않는다.

    SEED_SOURCE=fixture   (기본) fixtures/*.json
    SEED_SOURCE=dataset   확정 데이터셋 (현재 NotImplementedError)

**픽스처 파일을 직접 읽는 코드는 `FixtureProvider` 하나뿐이어야 한다.** 다른 곳에서 열면
데이터셋 교체 때 전부 찾아다녀야 한다. 런타임 조회는 `app/store.py`(provider 위의 인메모리 캐시)를
경유한다.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.config import FIXTURES_DIR, get_settings
from app.data.types import Customer, ScenarioSeed, SeedProduct
from contracts.common import OwnedAsset, SessionEvent

logger = logging.getLogger("app.data.provider")


@runtime_checkable
class SeedDataProvider(Protocol):
    """시드 데이터 접근 계약.

    `get_scenarios()` 는 최소 명세에 없지만 같은 seam 에 둔다. 시나리오의 라벨·대상 상품 메타를
    다른 경로로 읽으면 데이터셋 교체 지점이 두 개가 된다.
    """

    name: str

    def get_customers(self) -> list[Customer]: ...

    def get_products(self) -> list[SeedProduct]: ...

    def get_assets(self, customer_id: str | None = None) -> list[OwnedAsset]: ...

    def get_session_events(self, scenario_id: str) -> list[SessionEvent]: ...

    def get_scenarios(self) -> list[ScenarioSeed]: ...


#: last_code → 사람이 읽는 사이즈 체계 문구. 계약 `Product.size_system` 에 들어간다.
def size_system_from_last_code(last_code: str) -> str:
    code = last_code.strip().upper()
    if code.startswith("LAST-"):
        return f"EU 35-42 (하프 사이즈 제작 가능) / Last: {code.removeprefix('LAST-').title()}"
    if code.startswith("BAG-"):
        sizes = code.removeprefix("BAG-")
        return "One size" if sizes == "ONE" else f"Size {sizes.replace('/', ' / ')} cm"
    if code.startswith("CASE-"):
        return f"Case {code.removeprefix('CASE-').replace('/', 'mm / ')}mm"
    if code.startswith("BELT-"):
        return f"{code.removeprefix('BELT-').replace('/', ' / ')} cm"
    if code.startswith("WALLET-"):
        return "One size"
    return last_code


class FixtureProvider:
    """`fixtures/*.json` 기반 provider. 지금 사용하는 구현."""

    name = "fixture"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self.dir = fixtures_dir or FIXTURES_DIR
        self._products: list[SeedProduct] | None = None
        self._customers: list[Customer] | None = None
        self._assets: list[OwnedAsset] | None = None
        self._scenarios: list[ScenarioSeed] | None = None

    # ── 파일 로딩 (픽스처를 직접 읽는 유일한 지점) ──────────────
    def _read(self, filename: str) -> dict[str, Any]:
        path = self.dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"픽스처가 없다: {path} — fixtures/ 를 확인하라(SEED_SOURCE=fixture)"
            )
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"{filename} 최상위가 객체가 아니다")
        return loaded

    def get_products(self) -> list[SeedProduct]:
        if self._products is None:
            raw = self._read("products.json")["products"]
            products: list[SeedProduct] = []
            for item in raw:
                stock: dict[str, int] = {
                    str(k): int(v) for k, v in (item.get("stock_by_size") or {}).items()
                }
                products.append(
                    SeedProduct(
                        **{
                            **item,
                            "size_system": size_system_from_last_code(item["last_code"]),
                            "available_sizes": [s for s, q in stock.items() if q > 0],
                            "stock_by_size": stock,
                        }
                    )
                )
            self._products = products
        return list(self._products)

    def get_customers(self) -> list[Customer]:
        if self._customers is None:
            raw = self._read("customers.json")["customers"]
            self._customers = [Customer.model_validate(item) for item in raw]
        return list(self._customers)

    def get_assets(self, customer_id: str | None = None) -> list[OwnedAsset]:
        """개체 목록. `customer_id` 를 주면 그 고객 것만.

        `product_name` 은 픽스처에 없다(중복 저장 방지) — products.json 에서 조인해 채운다.
        """
        if self._assets is None:
            raw = self._read("assets.json")["assets"]
            by_product = {p.product_id: p for p in self.get_products()}
            assets: list[OwnedAsset] = []
            for item in raw:
                product = by_product.get(str(item["product_id"]))
                if product is None:
                    raise ValueError(
                        f"{item['asset_id']}: 존재하지 않는 product_id {item['product_id']}"
                    )
                assets.append(
                    OwnedAsset(
                        **{
                            **item,
                            "product_name": product.name,
                            "category": product.category,
                        }
                    )
                )
            self._assets = assets
        if customer_id is None:
            return list(self._assets)
        return [a for a in self._assets if a.customer_id == customer_id]

    def get_scenarios(self) -> list[ScenarioSeed]:
        if self._scenarios is None:
            raw = self._read("session_events.json")["scenarios"]
            self._scenarios = [ScenarioSeed.model_validate(item) for item in raw]
        return list(self._scenarios)

    def get_session_events(self, scenario_id: str) -> list[SessionEvent]:
        for scenario in self.get_scenarios():
            if scenario.scenario_id == scenario_id:
                return list(scenario.events)
        return []


class DatasetProvider:
    """확정 데이터셋 기반 provider — **스텁**.

    데이터셋이 확정되면 여기만 채운다. 복원 절차는 `scripts/_deferred/README.md` 에 있다.
    보류된 빌더(`scripts/_deferred/build_*.py`)가 만들던 산출물을 그대로 쓰거나, 새 로더를 붙인다.
    """

    name = "dataset"

    _MESSAGE = (
        "DatasetProvider 는 아직 구현되지 않았다(외부 데이터셋 미확정). "
        "SEED_SOURCE=fixture 로 실행하거나 scripts/_deferred/README.md 의 복원 절차를 따르라."
    )

    def get_customers(self) -> list[Customer]:
        raise NotImplementedError(self._MESSAGE)

    def get_products(self) -> list[SeedProduct]:
        raise NotImplementedError(self._MESSAGE)

    def get_assets(self, customer_id: str | None = None) -> list[OwnedAsset]:
        raise NotImplementedError(self._MESSAGE)

    def get_session_events(self, scenario_id: str) -> list[SessionEvent]:
        raise NotImplementedError(self._MESSAGE)

    def get_scenarios(self) -> list[ScenarioSeed]:
        raise NotImplementedError(self._MESSAGE)


def build_provider(source: str | None = None) -> SeedDataProvider:
    """`SEED_SOURCE` 에 따라 provider 를 만든다."""
    resolved = source or get_settings().seed_source
    if resolved == "dataset":
        logger.info("시드 소스: dataset (DatasetProvider)")
        return DatasetProvider()
    logger.info("시드 소스: fixture (%s)", FIXTURES_DIR)
    return FixtureProvider()


@lru_cache(maxsize=1)
def get_provider() -> SeedDataProvider:
    """프로세스 전역 provider."""
    return build_provider()


def reload_provider() -> SeedDataProvider:
    """픽스처를 고친 뒤 서버 재시작 없이 반영하기 위한 우회로."""
    get_provider.cache_clear()
    return get_provider()
