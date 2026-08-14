"""소유 개체 조회 어댑터 (백엔드).

목 구현은 `data/processed/customers.json`(Phase 2 산출물)을 읽는다.
HTTP 구현은 우리 계약 경로(`/assets/{id}`)를 먼저 시도하고, 실패하면 이미 만들어진 팀 백엔드 경로
(`/api/users/{id}/assets`)를 시도한 뒤 필드를 매핑한다.
"""

from __future__ import annotations

import time
from typing import Any

from app.adapters.base import AdapterBase, UpstreamError
from app.adapters.http_base import HttpAdapterBase
from app.config import REFERENCE_NOW
from app.domain import condition_score, next_service_months
from app.store import DataStore, get_store
from contracts.assets import CustomerAssetsResponse
from contracts.common import AssetPart, CustomerTier, ProductCategory, Severity


class MockAssetAdapter(AdapterBase):
    """Phase 2 산출물 기반 소유 개체 조회."""

    def __init__(self, store: DataStore | None = None) -> None:
        super().__init__(module="asset", mode="mock", target="data/processed/customers.json")
        self.store = store or get_store()

    def assets(self, customer_id: str) -> CustomerAssetsResponse:
        started = time.perf_counter()
        record = self.store.customer(customer_id)
        elapsed = (time.perf_counter() - started) * 1000
        if record is None:
            self.status.record_failure(elapsed, f"미등록 고객: {customer_id}")
            raise UpstreamError(f"고객을 찾을 수 없다: {customer_id}")
        self.status.record_success(elapsed, f"{len(record.assets)}개 개체")
        return CustomerAssetsResponse(
            customer_id=record.customer_id,
            tier=record.tier,
            assets=record.ranked_assets(),
        )


#: 팀 백엔드의 `wear_details` (횟수/불리언) → 우리 계약의 `findings` (부위/심각도/문장)
_WEAR_TO_FINDING: dict[str, tuple[AssetPart, Severity, str]] = {
    "scratches": (AssetPart.EXTERIOR, Severity.LOW, "표면 스크래치 확인"),
    "cracks": (AssetPart.EXTERIOR, Severity.HIGH, "표면 균열 발생"),
    "color_fade": (AssetPart.EXTERIOR, Severity.MEDIUM, "색 빠짐 진행"),
    "hardware_tarnish": (AssetPart.HARDWARE, Severity.MEDIUM, "금속 변색"),
    "lining_damage": (AssetPart.LINING, Severity.MEDIUM, "라이닝 손상"),
    "strap_wear": (AssetPart.HANDLE, Severity.MEDIUM, "스트랩/핸들 마모"),
}

_CATEGORY_ALIASES: dict[str, ProductCategory] = {
    "bag": ProductCategory.BAG,
    "bags": ProductCategory.BAG,
    "handbag": ProductCategory.BAG,
    "shoe": ProductCategory.SHOES,
    "shoes": ProductCategory.SHOES,
    "watch": ProductCategory.WATCH,
    "watches": ProductCategory.WATCH,
    "belt": ProductCategory.BELT,
    "belts": ProductCategory.BELT,
    "wallet": ProductCategory.WALLET,
    "wallets": ProductCategory.WALLET,
    "outerwear": ProductCategory.OUTERWEAR,
    "accessory": ProductCategory.ACCESSORY,
}


def _map_category(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.upper() in {c.value for c in ProductCategory}:
        return raw.upper()
    return _CATEGORY_ALIASES.get(raw.lower(), ProductCategory.ACCESSORY).value


def _findings_from_wear(wear: Any) -> list[dict[str, Any]]:
    if not isinstance(wear, dict):
        return []
    out: list[dict[str, Any]] = []
    for key, (part, severity, note) in _WEAR_TO_FINDING.items():
        value = wear.get(key)
        if isinstance(value, bool) and value:
            out.append({"part": part.value, "severity": severity.value, "note": note})
        elif isinstance(value, (int, float)) and value > 0:
            level = Severity.HIGH if value >= 3 else severity
            out.append(
                {"part": part.value, "severity": level.value, "note": f"{note} ({int(value)}건)"}
            )
    return out


def legacy_assets_mapper(raw: Any) -> dict[str, Any]:
    """팀 백엔드의 `GET /api/users/{id}/assets` 응답을 계약으로 옮긴다.

    차이 (docs/BACKEND_INTEGRATION.md 참고)
        user_id → customer_id, purchase_date → purchased_at, last_assessed → last_scanned_at,
        wear_details(횟수/불리언) → findings(부위/심각도/문장), tier 없음 → 개체 수로 추정,
        next_service_months 없음 → 컨디션 점수로 계산
    """
    if not isinstance(raw, dict):
        raise TypeError(f"dict 가 아님: {type(raw)}")
    customer_id = str(raw.get("customer_id") or raw.get("user_id") or "")
    raw_assets = raw.get("assets") or []
    assets: list[dict[str, Any]] = []
    for item in raw_assets:
        if not isinstance(item, dict):
            continue
        category = _map_category(item.get("category"))
        asset_id = str(item.get("asset_id"))
        score = int(item.get("condition_score") or 0)
        purchased = str(item.get("purchased_at") or item.get("purchase_date") or "")
        findings = item.get("findings")
        if not isinstance(findings, list) or not findings:
            findings = _findings_from_wear(item.get("wear_details") or item.get("wear_detail"))
        months = item.get("next_service_months")
        if months is None:
            months = next_service_months(score, ProductCategory(category), asset_id)
        assets.append(
            {
                "asset_id": asset_id,
                "customer_id": str(item.get("customer_id") or customer_id),
                "product_id": str(item.get("product_id") or ""),
                "product_name": str(item.get("product_name") or item.get("name") or ""),
                "category": category,
                "purchased_at": purchased,
                "condition_score": max(0, min(100, score)),
                "findings": findings,
                "next_service_months": int(months),
                "last_scanned_at": item.get("last_scanned_at") or item.get("last_assessed"),
            }
        )
    tier = raw.get("tier")
    if tier is None:
        count = len(assets)
        tier = (
            CustomerTier.VIP.value
            if count >= 8
            else CustomerTier.ESTABLISHED.value
            if count >= 3
            else CustomerTier.NEW.value
        )
    return {"customer_id": customer_id, "tier": tier, "assets": assets}


class HttpAssetAdapter(HttpAdapterBase):
    """실제 백엔드 호출 (`ASSET_BASE_URL`). 계약 경로 → 레거시 경로 순으로 시도한다."""

    def __init__(self) -> None:
        super().__init__(module="asset")

    def assets(self, customer_id: str) -> CustomerAssetsResponse:
        paths = (f"/assets/{customer_id}", f"/api/users/{customer_id}/assets")
        last_error: Exception | None = None
        for path in paths:
            try:
                return self.get_model(
                    path, CustomerAssetsResponse, legacy_mapper=legacy_assets_mapper
                )
            except UpstreamError as exc:
                last_error = exc
        raise UpstreamError(f"소유 개체 조회 실패({', '.join(paths)}): {last_error}")


def fallback_assets(customer_id: str, store: DataStore | None = None) -> CustomerAssetsResponse:
    """업스트림 실패 시 로컬 산출물로 대체한다. 데모에서 화면이 비지 않게 하는 마지막 방어선."""
    target = store or get_store()
    record = target.customer(customer_id)
    if record is None:
        return CustomerAssetsResponse(customer_id=customer_id, tier=CustomerTier.NEW, assets=[])
    return CustomerAssetsResponse(
        customer_id=record.customer_id, tier=record.tier, assets=record.ranked_assets()
    )


def recompute_condition(asset_id: str, category: ProductCategory, purchased_at: Any) -> int:
    """참고용: 구매 시각만 있을 때 컨디션을 재계산한다(레거시 응답 보완)."""
    from datetime import datetime

    if isinstance(purchased_at, str):
        purchased_at = datetime.fromisoformat(purchased_at)
    return condition_score(purchased_at, REFERENCE_NOW, category, asset_id)
