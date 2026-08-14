"""정규화 산출물 접근 계층 — 목 어댑터가 **실제 데이터**로 응답하게 하는 곳.

`data/processed/*.json` 이 사실의 원본이다(CLAUDE.md 참고). 목 어댑터는 이 스토어를 통해
Phase 2 산출물을 읽는다. 하드코딩된 더미 문자열은 쓰지 않는다.

프로세스 시작 시 한 번 읽어 메모리에 들고 있는다(40상품/30고객/60세션 규모라 문제 없다).
파일이 없으면 빈 스토어로 뜨고 `/health/detail` 에서 그 사실이 보인다 — 서버가 죽지 않는 편이
데모에 안전하다.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import PROCESSED_DIR
from contracts.common import CustomerTier, OwnedAsset, Product, SessionEvent

logger = logging.getLogger("app.store")

CATALOG_PATH = PROCESSED_DIR / "catalog_luxury.json"
CUSTOMERS_PATH = PROCESSED_DIR / "customers.json"
SESSIONS_PATH = PROCESSED_DIR / "sessions.json"


@dataclass
class CustomerRecord:
    """고객 1명 + 소유 개체."""

    customer_id: str
    display_name: str
    tier: CustomerTier
    purchase_count: int
    assets: list[OwnedAsset] = field(default_factory=list)

    def ranked_assets(self) -> list[OwnedAsset]:
        """상담에서 인용할 우선순위. 서비스 임박 → 컨디션 낮은 순."""
        return sorted(self.assets, key=lambda a: (a.next_service_months, a.condition_score))


@dataclass
class SessionRecord:
    """이탈 세션 1건."""

    session_id: str
    customer_id: str
    target_product_id: str
    hesitation_label: str
    label_confidence: float
    profile: str
    events: list[SessionEvent] = field(default_factory=list)
    signals: list[dict[str, Any]] = field(default_factory=list)


class DataStore:
    """카탈로그·고객·세션을 한 번 읽어 들고 있는 읽기 전용 스토어."""

    def __init__(self, processed_dir: Path | None = None) -> None:
        base = processed_dir or PROCESSED_DIR
        self.catalog_path = base / "catalog_luxury.json"
        self.customers_path = base / "customers.json"
        self.sessions_path = base / "sessions.json"

        self.products: dict[str, Product] = {}
        self.customers: dict[str, CustomerRecord] = {}
        self.sessions: dict[str, SessionRecord] = {}
        self.assets: dict[str, OwnedAsset] = {}
        self.load_errors: list[str] = []
        self.generated_with: dict[str, Any] = {}
        self._load()

    # ── 로딩 ──────────────────────────────────────────────────
    def _read(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            msg = f"{path.name} 없음 (make data 를 실행하라)"
            self.load_errors.append(msg)
            logger.warning("스토어 로드 실패: %s", msg)
            return None
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            self.load_errors.append(f"{path.name} 읽기 실패: {exc}")
            logger.warning("스토어 로드 실패: %s (%s)", path.name, exc)
            return None
        return loaded if isinstance(loaded, dict) else None

    def _load(self) -> None:
        catalog = self._read(self.catalog_path)
        if catalog:
            for item in catalog.get("items", []):
                product = Product.model_validate(item)
                self.products[product.product_id] = product
            self.generated_with["catalog"] = catalog.get("generated_with", {})

        customers = self._read(self.customers_path)
        if customers:
            for raw in customers.get("customers", []):
                assets = [OwnedAsset.model_validate(a) for a in raw.get("assets", [])]
                record = CustomerRecord(
                    customer_id=str(raw["customer_id"]),
                    display_name=str(raw.get("display_name", "")),
                    tier=CustomerTier(raw["tier"]),
                    purchase_count=int(raw.get("purchase_count", 0)),
                    assets=assets,
                )
                self.customers[record.customer_id] = record
                for asset in assets:
                    self.assets[asset.asset_id] = asset
            self.generated_with["customers"] = customers.get("generated_with", {})

        sessions = self._read(self.sessions_path)
        if sessions:
            for raw in sessions.get("sessions", []):
                session_record = SessionRecord(
                    session_id=str(raw["session_id"]),
                    customer_id=str(raw["customer_id"]),
                    target_product_id=str(raw["target_product_id"]),
                    hesitation_label=str(raw["hesitation_label"]),
                    label_confidence=float(raw.get("label_confidence", 0.0)),
                    profile=str(raw.get("profile", "")),
                    events=[SessionEvent.model_validate(e) for e in raw.get("events", [])],
                    signals=list(raw.get("signals", [])),
                )
                self.sessions[session_record.session_id] = session_record
            self.generated_with["sessions"] = sessions.get("generated_with", {})

    # ── 조회 ──────────────────────────────────────────────────
    @property
    def ready(self) -> bool:
        return bool(self.products and self.customers)

    def product(self, product_id: str) -> Product | None:
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

    def cheaper_alternative(self, product_id: str) -> Product | None:
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
        """대상 상품과 같은 카테고리의 소유 개체(사이즈·라스트 상담의 근거)."""
        target = self.product(product_id)
        if target is None:
            return []
        return [a for a in self.customer_assets(customer_id) if a.category is target.category]

    def stats(self) -> dict[str, Any]:
        """`/health/detail` 노출용 요약."""
        return {
            "products": len(self.products),
            "customers": len(self.customers),
            "assets": len(self.assets),
            "sessions": len(self.sessions),
            "load_errors": self.load_errors,
            "generated_with": self.generated_with,
        }


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    """프로세스 전역 스토어."""
    return DataStore()


def reload_store() -> DataStore:
    """데이터를 다시 빌드한 뒤 서버를 재시작하지 않고 반영하기 위한 우회로."""
    get_store.cache_clear()
    return get_store()
