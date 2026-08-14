"""런타임 조회 캐시 — `SeedDataProvider` 위에 얹은 얇은 인메모리 층.

목 어댑터·오케스트레이터·Lab·데모는 **이 스토어(→ provider)만** 통해 데이터를 본다.
픽스처 파일을 여는 코드는 `app/data/provider.py` 의 `FixtureProvider` 하나뿐이므로,
데이터셋이 확정되면 `DatasetProvider` 만 채우고 `SEED_SOURCE=dataset` 으로 바꾸면 된다.

규모가 작아(상품 12 / 고객 6 / 개체 18 / 시나리오 3) 프로세스 시작 시 한 번 읽어 들고 있는다.
provider 가 실패하면 빈 스토어로 뜨고 그 사실이 `/health/detail` 에 보인다 — 서버가 죽는 편보다
데모에 안전하다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.data.provider import SeedDataProvider, get_provider
from app.data.types import Customer, ScenarioSeed, SeedProduct
from app.intent_rules import classify
from contracts.common import CustomerTier, OwnedAsset, SessionEvent

logger = logging.getLogger("app.store")


@dataclass
class CustomerRecord:
    """고객 1명 + 소유 개체."""

    customer_id: str
    display_name: str
    tier: CustomerTier
    purchase_count: int
    assets: list[OwnedAsset] = field(default_factory=list)
    seed: Customer | None = None

    def ranked_assets(self) -> list[OwnedAsset]:
        """상담에서 인용할 우선순위. 서비스 임박 → 컨디션 낮은 순."""
        return sorted(self.assets, key=lambda a: (a.next_service_months, a.condition_score))

    @property
    def size_profile(self) -> dict[str, str]:
        return self.seed.size_profile if self.seed else {}


@dataclass
class SessionRecord:
    """세션 시나리오 1건. 라벨은 이벤트 시퀀스에 규칙을 적용해 도출한다(손으로 적지 않는다)."""

    session_id: str
    customer_id: str
    target_product_id: str
    hesitation_label: str
    label_confidence: float
    profile: str
    events: list[SessionEvent] = field(default_factory=list)
    signals: list[dict[str, Any]] = field(default_factory=list)
    title: str = ""
    label_hint: str = ""

    @property
    def label_matches_hint(self) -> bool:
        return not self.label_hint or self.label_hint == self.hesitation_label


class DataStore:
    """provider 결과를 조회하기 쉬운 형태로 들고 있는 읽기 전용 스토어."""

    def __init__(self, provider: SeedDataProvider | None = None) -> None:
        self.provider: SeedDataProvider = provider or get_provider()
        self.products: dict[str, SeedProduct] = {}
        self.customers: dict[str, CustomerRecord] = {}
        self.sessions: dict[str, SessionRecord] = {}
        self.assets: dict[str, OwnedAsset] = {}
        self.load_errors: list[str] = []
        self._load()

    # ── 로딩 ──────────────────────────────────────────────────
    def _load(self) -> None:
        try:
            for product in self.provider.get_products():
                self.products[product.product_id] = product
        except (OSError, ValueError, NotImplementedError) as exc:
            self.load_errors.append(f"상품 로드 실패: {exc}")
            logger.warning("상품 로드 실패: %s", exc)

        try:
            assets = self.provider.get_assets()
            for asset in assets:
                self.assets[asset.asset_id] = asset
            for customer in self.provider.get_customers():
                owned = [a for a in assets if a.customer_id == customer.customer_id]
                self.customers[customer.customer_id] = CustomerRecord(
                    customer_id=customer.customer_id,
                    display_name=customer.name,
                    tier=customer.tier,
                    purchase_count=len(owned),
                    assets=owned,
                    seed=customer,
                )
        except (OSError, ValueError, NotImplementedError) as exc:
            self.load_errors.append(f"고객/개체 로드 실패: {exc}")
            logger.warning("고객/개체 로드 실패: %s", exc)

        try:
            for scenario in self.provider.get_scenarios():
                self.sessions[scenario.scenario_id] = self._to_session(scenario)
        except (OSError, ValueError, NotImplementedError) as exc:
            self.load_errors.append(f"시나리오 로드 실패: {exc}")
            logger.warning("시나리오 로드 실패: %s", exc)

    def _to_session(self, scenario: ScenarioSeed) -> SessionRecord:
        result = classify(scenario.events)
        if scenario.label_hint.value != result.hesitation_type.value:
            logger.warning(
                "시나리오 %s: 규칙 라벨 %s ≠ 픽스처 힌트 %s (validate_fixtures 로 확인하라)",
                scenario.scenario_id,
                result.hesitation_type.value,
                scenario.label_hint.value,
            )
        return SessionRecord(
            session_id=scenario.scenario_id,
            customer_id=scenario.customer_id,
            target_product_id=scenario.target_product_id,
            hesitation_label=result.hesitation_type.value,
            label_confidence=result.confidence,
            profile="fixture",
            events=list(scenario.events),
            signals=[s.model_dump(mode="json") for s in result.signals],
            title=scenario.title,
            label_hint=scenario.label_hint.value,
        )

    # ── 조회 ──────────────────────────────────────────────────
    @property
    def ready(self) -> bool:
        return bool(self.products and self.customers)

    @property
    def seed_source(self) -> str:
        return getattr(self.provider, "name", "unknown")

    def product(self, product_id: str) -> SeedProduct | None:
        return self.products.get(product_id)

    def customer(self, customer_id: str) -> CustomerRecord | None:
        return self.customers.get(customer_id)

    def asset(self, asset_id: str) -> OwnedAsset | None:
        return self.assets.get(asset_id)

    def customer_assets(self, customer_id: str) -> list[OwnedAsset]:
        record = self.customer(customer_id)
        return list(record.assets) if record else []

    def sessions_for(self, customer_id: str) -> list[SessionRecord]:
        return [s for s in self.sessions.values() if s.customer_id == customer_id]

    def sessions_by_label(self, label: str) -> list[SessionRecord]:
        return [s for s in self.sessions.values() if s.hesitation_label == label]

    def cheaper_alternative(self, product_id: str) -> SeedProduct | None:
        """같은 카테고리에서 한 단계 저렴한 상품(가격 상담용)."""
        target = self.product(product_id)
        if target is None:
            return None
        same = sorted(
            (p for p in self.products.values() if p.category is target.category),
            key=lambda p: p.price_krw,
        )
        cheaper = [p for p in same if p.price_krw < target.price_krw]
        return cheaper[-1] if cheaper else None

    def same_category_assets(self, customer_id: str, product_id: str) -> list[OwnedAsset]:
        """대상 상품과 같은 카테고리의 소유 개체(사이즈·소재 상담의 근거)."""
        target = self.product(product_id)
        if target is None:
            return []
        return [a for a in self.customer_assets(customer_id) if a.category is target.category]

    def same_last_assets(self, customer_id: str, product_id: str) -> list[OwnedAsset]:
        """대상 상품과 **같은 사이즈 체계(last_code)** 의 소유 개체. 사이즈 상담의 직접 근거다."""
        target = self.product(product_id)
        if target is None:
            return []
        out: list[OwnedAsset] = []
        for asset in self.customer_assets(customer_id):
            owned_product = self.product(asset.product_id)
            if owned_product is not None and owned_product.last_code == target.last_code:
                out.append(asset)
        return out

    def stats(self) -> dict[str, Any]:
        """`/health/detail` 노출용 요약."""
        label_mismatch = [s.session_id for s in self.sessions.values() if not s.label_matches_hint]
        return {
            "seed_source": self.seed_source,
            "products": len(self.products),
            "customers": len(self.customers),
            "assets": len(self.assets),
            "sessions": len(self.sessions),
            "load_errors": self.load_errors,
            "label_mismatch": label_mismatch,
        }


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    """프로세스 전역 스토어."""
    return DataStore()


def reload_store() -> DataStore:
    """픽스처를 고친 뒤 서버 재시작 없이 반영하기 위한 우회로."""
    from app.data.provider import reload_provider

    get_store.cache_clear()
    reload_provider()
    return get_store()
