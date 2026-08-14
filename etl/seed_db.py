"""
etl/seed_db.py - CSV 데이터를 SQLite DB에 로드하는 시딩 스크립트
실행: python etl/seed_db.py
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import Base, User, Product, Asset, SessionEvent, ConditionGrade, EventType

DATA_DIR   = Path(__file__).parent.parent / "data"
DB_PATH    = Path(__file__).parent.parent / "luxury_clienteling.db"
DB_URL     = f"sqlite+aiosqlite:///{DB_PATH}"


# ──────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────

def _safe_datetime(val) -> datetime:
    if pd.isna(val):
        return datetime.utcnow()
    return datetime.fromisoformat(str(val))


def _safe_json(val) -> dict:
    if pd.isna(val):
        return {}
    if isinstance(val, dict):
        return val
    try:
        return json.loads(val)
    except Exception:
        return {}


# ──────────────────────────────────────────────────────
# Loaders
# ──────────────────────────────────────────────────────

async def seed_products(session: AsyncSession):
    df = pd.read_csv(DATA_DIR / "products.csv")
    for _, row in df.iterrows():
        session.add(Product(
            product_id   = row["product_id"],
            name         = row["name"],
            brand        = row["brand"],
            category     = row["category"],
            sub_category = row.get("sub_category"),
            material     = row.get("material"),
            color        = row.get("color"),
            price_usd    = float(row["price_usd"]),
            launch_year  = int(row["launch_year"]) if not pd.isna(row.get("launch_year")) else None,
            sku          = row.get("sku"),
            description  = row.get("description"),
            extra_meta   = _safe_json(row.get("extra_meta")),
        ))
    await session.commit()
    print(f"  ✅ Products: {len(df)}건 삽입")


async def seed_users(session: AsyncSession):
    df = pd.read_csv(DATA_DIR / "users.csv")
    for _, row in df.iterrows():
        session.add(User(
            user_id    = row["user_id"],
            name       = row["name"],
            email      = row["email"],
            tier       = row["tier"],
            country    = row.get("country"),
            created_at = _safe_datetime(row.get("created_at")),
            is_active  = bool(row.get("is_active", True)),
        ))
    await session.commit()
    print(f"  ✅ Users: {len(df)}건 삽입")


async def seed_assets(session: AsyncSession):
    df = pd.read_csv(DATA_DIR / "assets.csv")
    for _, row in df.iterrows():
        grade_raw = str(row["condition_grade"]).strip()
        grade = ConditionGrade(grade_raw)
        session.add(Asset(
            asset_id         = row["asset_id"],
            user_id          = row["user_id"],
            product_id       = row["product_id"],
            purchase_date    = _safe_datetime(row["purchase_date"]),
            purchase_price   = float(row["purchase_price"]) if not pd.isna(row.get("purchase_price")) else None,
            purchase_channel = row.get("purchase_channel"),
            condition_score  = int(row["condition_score"]),
            condition_grade  = grade,
            wear_details     = _safe_json(row.get("wear_details")),
            last_assessed    = _safe_datetime(row.get("last_assessed")),
            notes            = row.get("notes") if not pd.isna(row.get("notes", float("nan"))) else None,
        ))
    await session.commit()
    print(f"  ✅ Assets: {len(df)}건 삽입")


async def seed_events(session: AsyncSession):
    df = pd.read_csv(DATA_DIR / "session_events.csv")
    for _, row in df.iterrows():
        etype = EventType(str(row["event_type"]).strip())
        product_id = row.get("product_id")
        if pd.isna(product_id):
            product_id = None
        session.add(SessionEvent(
            event_id    = row["event_id"],
            user_id     = row["user_id"],
            session_id  = row["session_id"],
            product_id  = product_id,
            event_type  = etype,
            event_at    = _safe_datetime(row["event_at"]),
            duration_sec= float(row["duration_sec"]) if not pd.isna(row.get("duration_sec")) else None,
            device      = row.get("device"),
            referrer    = row.get("referrer"),
            extra_data  = _safe_json(row.get("extra_data")),
        ))
    await session.commit()
    print(f"  ✅ SessionEvents: {len(df)}건 삽입")


# ──────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────

async def main():
    print(f"🗄️  DB 초기화 중: {DB_PATH}")
    engine = create_async_engine(DB_URL, echo=False,
        connect_args={"check_same_thread": False})

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)   # 기존 테이블 초기화
        await conn.run_sync(Base.metadata.create_all)
    print("  ✅ 스키마 생성 완료")

    Session = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with Session() as session:
        print("\n📥 데이터 삽입 시작...")
        await seed_products(session)
        await seed_users(session)
        await seed_assets(session)
        await seed_events(session)

    await engine.dispose()
    print(f"\n🎉 시딩 완료! → {DB_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
