"""정규화 산출물 → SQLite 적재.

`data/processed/*.json` 이 사실의 원본이고 SQLite 는 조회 편의를 위한 사본이다.
그래서 이 스크립트는 언제든 다시 돌릴 수 있다(기본 동작이 drop & create).

    python -m scripts.seed_db
    python -m scripts.seed_db --keep    # 테이블을 지우지 않고 upsert (Lab 결과 보존)
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from app.config import get_settings
from app.db import init_db, session_scope
from app.models import AssetRow, CustomerRow, ProductRow, SessionRow
from contracts.common import OwnedAsset, Product
from scripts.common import CATALOG_PATH, CUSTOMERS_PATH, SESSIONS_PATH, banner, read_json


def parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def main() -> int:
    ap = argparse.ArgumentParser(description="정규화 산출물을 SQLite 에 적재")
    ap.add_argument(
        "--keep", action="store_true", help="테이블을 지우지 않고 덮어쓴다(Lab 결과 보존)"
    )
    args = ap.parse_args()

    banner("SQLite 시드")
    missing = [p.name for p in (CATALOG_PATH, CUSTOMERS_PATH, SESSIONS_PATH) if not p.exists()]
    if missing:
        print(f"  ! 산출물 없음: {', '.join(missing)} → `make data` 를 먼저 실행하라")
        return 1

    init_db(drop=not args.keep)
    settings = get_settings()

    catalog = [Product.model_validate(i) for i in read_json(CATALOG_PATH)["items"]]
    customers = read_json(CUSTOMERS_PATH)["customers"]
    sessions = read_json(SESSIONS_PATH)["sessions"]

    with session_scope() as db:
        for product in catalog:
            db.merge(
                ProductRow(
                    product_id=product.product_id,
                    name=product.name,
                    category=product.category.value,
                    collection=product.collection,
                    material=product.material,
                    color=product.color,
                    price_krw=product.price_krw,
                    size_system=product.size_system,
                    available_sizes=product.available_sizes,
                    care_notes=product.care_notes,
                    image_path=product.image_path,
                )
            )

        asset_total = 0
        for cust in customers:
            db.merge(
                CustomerRow(
                    customer_id=cust["customer_id"],
                    display_name=cust["display_name"],
                    tier=cust["tier"],
                    purchase_count=int(cust["purchase_count"]),
                    asset_count=int(cust["asset_count"]),
                )
            )
            for raw in cust["assets"]:
                asset = OwnedAsset.model_validate(raw)
                db.merge(
                    AssetRow(
                        asset_id=asset.asset_id,
                        customer_id=asset.customer_id,
                        product_id=asset.product_id,
                        product_name=asset.product_name,
                        category=asset.category.value,
                        purchased_at=asset.purchased_at,
                        condition_score=asset.condition_score,
                        findings=[f.model_dump(mode="json") for f in asset.findings],
                        next_service_months=asset.next_service_months,
                        last_scanned_at=asset.last_scanned_at,
                    )
                )
                asset_total += 1

        for sess in sessions:
            db.merge(
                SessionRow(
                    session_id=sess["session_id"],
                    customer_id=sess["customer_id"],
                    customer_tier=sess["customer_tier"],
                    target_product_id=sess["target_product_id"],
                    hesitation_label=sess["hesitation_label"],
                    label_rule=sess["label_rule"],
                    label_confidence=float(sess["label_confidence"]),
                    profile=sess["profile"],
                    abandoned=bool(sess["abandoned"]),
                    events=sess["events"],
                    signals=sess["signals"],
                )
            )

    print(f"  DB: {settings.db_path}")
    print(
        f"  적재 — 상품 {len(catalog)} / 고객 {len(customers)} / 개체 {asset_total} / "
        f"세션 {len(sessions)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
