"""SQLite 엔진과 세션 팩토리.

해커톤 스케일이라 동기 SQLAlchemy 를 쓴다. FastAPI 핸들러에서 짧게 열고 닫는다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Base


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """프로세스 전역 엔진. SQLite 는 스레드 간 공유를 위해 check_same_thread=False 로 연다."""
    settings = get_settings()
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        future=True,
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def init_db(drop: bool = False) -> None:
    """테이블 생성. `drop=True` 면 전부 지우고 다시 만든다(마이그레이션 대신)."""
    engine = get_engine()
    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """트랜잭션 스코프. 예외 시 롤백한다."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI 의존성."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()
