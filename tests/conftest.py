"""테스트 공통 설정.

**테스트는 실제 `data/app.db` 를 건드리지 않는다.** LLM 사용량 기록이 예산 집계에 들어가므로,
테스트가 데모용 DB 에 행을 남기면 `/ops` 의 누적 사용액이 오염된다. 임시 DB 로 격리한다.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(scope="session", autouse=True)
def isolated_db(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """세션 전체에서 임시 SQLite 를 쓰도록 강제한다."""
    db_path = tmp_path_factory.mktemp("db") / "test.db"
    os.environ["DB_PATH"] = str(db_path)

    from app.config import get_settings
    from app.db import get_engine, get_sessionmaker, init_db
    from app.llm.budget import get_budget

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    init_db(drop=True)
    get_budget().invalidate()
    yield
