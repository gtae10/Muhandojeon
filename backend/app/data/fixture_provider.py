"""
app/data/fixture_provider.py
루트 fixtures/*.json (customers.json, assets.json, products.json) 을 읽는
backend 서비스 내 유일한 지점.

루트 통합 레이어의 app/data/provider.py 와 같은 손으로 쓴 시드를 그대로 재사용한다
(fixtures/customers.json, fixtures/assets.json, fixtures/products.json) — 데이터를
중복 보관하지 않는다. 여기서 직접 읽는 대신 다른 곳에서 fixtures/ 를 열면 안 된다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

# backend/app/data/fixture_provider.py 기준 parents[3] == 저장소 루트(Muhandojeon/)
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES_DIR = _REPO_ROOT / "fixtures"


def _read(filename: str) -> dict[str, Any]:
    path = _FIXTURES_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"픽스처가 없다: {path}")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{filename} 최상위가 객체가 아니다")
    return loaded


@lru_cache(maxsize=1)
def _products_by_id() -> dict[str, dict[str, Any]]:
    raw = _read("products.json")["products"]
    return {str(p["product_id"]): p for p in raw}


@lru_cache(maxsize=1)
def _customers_by_id() -> dict[str, dict[str, Any]]:
    raw = _read("customers.json")["customers"]
    return {str(c["customer_id"]): c for c in raw}


@lru_cache(maxsize=1)
def _assets_by_id() -> dict[str, dict[str, Any]]:
    raw = _read("assets.json")["assets"]
    return {str(a["asset_id"]): _enrich_asset(a) for a in raw}


def _enrich_asset(asset_raw: dict[str, Any]) -> dict[str, Any]:
    """product_id 로 products.json 을 조인해 product_name/category 를 채운다."""
    product = _products_by_id().get(str(asset_raw.get("product_id")))
    enriched = dict(asset_raw)
    if product is not None:
        enriched.setdefault("product_name", product.get("name"))
        enriched.setdefault("category", product.get("category"))
    return enriched


def get_customer(customer_id: str) -> dict[str, Any] | None:
    """customer_id → 고객 raw dict. 없으면 None."""
    return _customers_by_id().get(customer_id)


def get_assets_for_customer(customer_id: str) -> list[dict[str, Any]]:
    """고객이 소유한 개체 raw dict 목록 (product_name/category 조인 포함)."""
    return [a for a in _assets_by_id().values() if a.get("customer_id") == customer_id]


def get_asset(asset_id: str) -> dict[str, Any] | None:
    """asset_id → 개체 raw dict. 없으면 None."""
    return _assets_by_id().get(asset_id)


def get_all_asset_ids(customer_id: str | None = None) -> list[str]:
    """customer_id 가 주어지면 그 고객 소유 개체 id만, 아니면 전체 개체 id."""
    if customer_id is None:
        return list(_assets_by_id().keys())
    return [a["asset_id"] for a in get_assets_for_customer(customer_id)]


def compute_tier(customer_id: str) -> str:
    """고객 등급.

    fixtures/customers.json 에 손으로 지정된 tier 를 우선 쓰고, 고객이 픽스처에
    없으면(레거시 호출 등) 보유 개체 수로 추정한다: 8+→VIP / 3~7→ESTABLISHED / 그 외→NEW.
    """
    customer = get_customer(customer_id)
    if customer is not None and customer.get("tier"):
        return str(customer["tier"])

    asset_count = len(get_assets_for_customer(customer_id))
    if asset_count >= 8:
        return "VIP"
    if asset_count >= 3:
        return "ESTABLISHED"
    return "NEW"
