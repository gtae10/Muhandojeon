"""FastAPI 앱 — 통합 서버.

한 프로세스가 다음을 모두 제공한다.
    - `POST /session/advise` : 프론트의 단일 진입점 (오케스트레이터)
    - 계약의 5개 모듈 엔드포인트 : 목 또는 실서버 프록시
    - `/catalog`, `/customers`, `/sessions` : 화면 채우기용 읽기 전용
    - `/lab` : Persona Bot Lab 대시보드
    - `/health/detail` : 발표 직전 5초 점검

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import PROCESSED_DIR, get_settings
from app.db import init_db
from app.routers import catalog, demo, health, lab, modules, session
from app.store import get_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    init_db()
    store = get_store()
    logger.info(
        "기동 — adapter_mode=%s demo_mode=%s data=%s 상품 %d / 고객 %d / 세션 %d",
        settings.adapter_mode,
        settings.demo_mode,
        settings.data_source,
        len(store.products),
        len(store.customers),
        len(store.sessions),
    )
    for err in store.load_errors:
        logger.warning("데이터 로드 경고: %s", err)
    yield


app = FastAPI(
    title="Luxe Clienteling — 통합/데모 API",
    version="0.1.0",
    description=(
        "럭셔리 개체지문 + AI 클라이언텔링의 통합 레이어. 계약은 docs/CONTRACTS.md, "
        "데이터 출처는 docs/DATA_PROVENANCE.md 참고."
    ),
    lifespan=lifespan,
)

# 프론트가 다른 포트에서 뜨는 해커톤 환경이라 전면 허용한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Degraded", "X-Owned-Assets-Used"],
)

app.include_router(health.router)
app.include_router(session.router)
app.include_router(modules.router)
app.include_router(catalog.router)
app.include_router(lab.router)
app.include_router(demo.router)

if PROCESSED_DIR.exists():
    app.mount("/static", StaticFiles(directory=PROCESSED_DIR), name="static")


@app.get("/", tags=["Health"], summary="진입점 안내")
def root() -> dict[str, Any]:
    return {
        "service": "luxe-clienteling integration layer",
        "entrypoint": "POST /session/advise",
        "docs": "/docs",
        "health": "/health/detail",
        "lab": "/lab",
        "contracts": "docs/CONTRACTS.md",
    }
