"""
app/routers/assets.py
GET /assets/{customer_id}  — 계약 경로 (백엔드 담당)
GET /api/users/{user_id}/assets — 레거시 경로 (통합 레이어 자동 매핑)

docs/CONTRACTS.md:
    GET /assets/{customer_id} → CustomerAssetsResponse
    - customer_id, tier, assets[]

docs/BACKEND_INTEGRATION.md 레거시 매핑:
    user_id     ↔ customer_id
    purchase_date ↔ purchased_at
    last_assessed ↔ last_scanned_at
    tier: 개체 수로 추정 (8+→VIP / 3~7→ESTABLISHED / 그 외→NEW)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.data.fixture_provider import (
    get_assets_for_customer,
    get_customer,
    compute_tier,
)
from app.schemas.models import (
    CustomerAssetsResponse,
    OwnedAsset,
    Finding,
)

router = APIRouter(tags=["Assets"])


def _parse_datetime(val: str | None) -> datetime | None:
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def _build_owned_asset(asset_raw: dict) -> OwnedAsset:
    """픽스처 raw dict → OwnedAsset 스키마 변환."""
    findings = [
        Finding(
            part=f.get("part", "exterior"),
            severity=f.get("severity", "LOW"),
            note=f.get("note", ""),
        )
        for f in asset_raw.get("findings", [])
    ]

    # purchased_at: purchased_at 또는 purchase_date (레거시)
    purchased_at_raw = (
        asset_raw.get("purchased_at")
        or asset_raw.get("purchase_date")
    )
    purchased_at = _parse_datetime(purchased_at_raw) or datetime.now()

    last_scanned_at = _parse_datetime(
        asset_raw.get("last_scanned_at") or asset_raw.get("last_assessed")
    )

    score = asset_raw.get("condition_score", 75)
    nsm = asset_raw.get("next_service_months", 0)

    return OwnedAsset(
        asset_id=asset_raw["asset_id"],
        customer_id=asset_raw["customer_id"],
        product_id=asset_raw["product_id"],
        product_name=asset_raw.get("product_name", "Unknown"),
        category=asset_raw.get("category", "BAG"),
        purchased_at=purchased_at,
        condition_score=score,
        findings=findings,
        next_service_months=nsm,
        last_scanned_at=last_scanned_at,
    )


# ──────────────────────────────────────────────
# 계약 경로: GET /assets/{customer_id}
# ──────────────────────────────────────────────

@router.get("/assets/{customer_id}", response_model=CustomerAssetsResponse, tags=["Assets (Contract)"])
async def get_assets_by_contract(customer_id: str):
    """
    고객 소유 개체 목록 + 컨디션 반환 (계약 형식).

    백엔드 담당 엔드포인트.
    통합 레이어는 이 경로를 먼저 시도하고, 실패 시 레거시 경로를 시도한다.

    정렬: 오케스트레이터가 담당하므로 여기서 정렬하지 않는다.
    """
    assets_raw = get_assets_for_customer(customer_id)
    tier = compute_tier(customer_id)

    owned_assets = [_build_owned_asset(a) for a in assets_raw]

    return CustomerAssetsResponse(
        customer_id=customer_id,
        tier=tier,
        assets=owned_assets,
    )


# ──────────────────────────────────────────────
# 레거시 경로: GET /api/users/{user_id}/assets
# (통합 레이어의 legacy-mapped 경로와 호환)
# ──────────────────────────────────────────────

@router.get("/api/users/{user_id}/assets", tags=["Assets (Legacy)"])
async def get_user_assets_legacy(user_id: str):
    """
    고객 소유 자산 목록 반환 (레거시 필드명 유지).
    통합 레이어의 어댑터가 user_id → customer_id 로 매핑해 이 경로를 호출할 수 있다.
    응답은 계약 형식과 레거시 필드를 모두 포함한다 (어댑터가 자동 흡수).
    """
    assets_raw = get_assets_for_customer(user_id)
    tier = compute_tier(user_id)

    legacy_assets = []
    for a in assets_raw:
        purchased_at_raw = a.get("purchased_at") or a.get("purchase_date")
        purchased_at = _parse_datetime(purchased_at_raw)
        last_assessed = _parse_datetime(
            a.get("last_scanned_at") or a.get("last_assessed")
        )

        # wear_details: 기존 wear_details JSON + findings에서 생성
        wear_details = a.get("wear_details") or _findings_to_wear_details(
            a.get("findings", [])
        )

        legacy_assets.append({
            # 레거시 필드
            "asset_id": a["asset_id"],
            "user_id": user_id,
            "product_id": a["product_id"],
            "product_name": a.get("product_name", "Unknown"),
            "category": a.get("category", "BAG"),
            "purchase_date": purchased_at.isoformat() if purchased_at else None,
            "last_assessed": last_assessed.isoformat() if last_assessed else None,
            "condition_score": a.get("condition_score", 75),
            "condition_grade": _score_to_grade(a.get("condition_score", 75)),
            "wear_details": wear_details,
            # 계약 필드 (레거시 매핑 시 어댑터가 처리)
            "customer_id": user_id,
            "purchased_at": purchased_at.isoformat() if purchased_at else None,
            "last_scanned_at": last_assessed.isoformat() if last_assessed else None,
            "findings": a.get("findings", []),
            "next_service_months": a.get("next_service_months", 0),
        })

    return {
        "user_id": user_id,
        "customer_id": user_id,
        "tier": tier,
        "total": len(legacy_assets),
        "assets": legacy_assets,
    }


def _score_to_grade(score: int) -> str:
    if score >= 90:
        return "Mint"
    if score >= 75:
        return "Excellent"
    if score >= 55:
        return "Good"
    if score >= 30:
        return "Fair"
    return "Poor"


def _findings_to_wear_details(findings: list[dict]) -> dict:
    """findings 목록 → wear_details 형태로 변환 (레거시 호환)."""
    wd: dict = {
        "scratches": 0,
        "cracks": 0,
        "color_fade": False,
        "hardware_tarnish": False,
        "lining_damage": False,
        "strap_wear": False,
    }
    for f in findings:
        part = f.get("part", "")
        severity = f.get("severity", "LOW")
        if part in ("exterior", "corner") and severity in ("MEDIUM", "HIGH"):
            wd["scratches"] += 1
        if part == "hardware":
            wd["hardware_tarnish"] = True
        if part == "lining":
            wd["lining_damage"] = True
        if part in ("strap", "handle"):
            wd["strap_wear"] = True
    return wd


# (AssetListResponse 는 구형 routers/assets.py 에서만 사용)
