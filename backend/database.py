"""
database.py - DB 엔진 및 세션 팩토리
"""

import os
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from models import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./luxury_clienteling.db"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    # SQLite 한정 설정 (PostgreSQL 사용 시 제거)
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def init_db():
    """앱 시작 시 테이블 자동 생성"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """FastAPI Depends용 세션 제너레이터"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
