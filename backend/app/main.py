"""
app/main.py - FastAPI 앱 진입점

실행: uvicorn app.main:app --reload --port 8001

계약 엔드포인트 (백엔드 담당, docs/CONTRACTS.md):
    GET  /assets/{customer_id}    → 고객 소유 개체 + 컨디션
    POST /fingerprint/match       → 개체 지문 매칭
    POST /condition/score         → 컨디션 점수 분석

레거시 엔드포인트 (통합 레이어 어댑터 호환):
    GET  /api/users/{user_id}/assets
    POST /api/fingerprint
    POST /api/chat
    GET  /api/products/{product_id}

통합 레이어와 연결:
    ASSET_ADAPTER=http ASSET_BASE_URL=http://localhost:8001 make dev
    CONDITION_ADAPTER=http CONDITION_BASE_URL=http://localhost:8001 make dev
"""

from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import products, fingerprint, chat
from app.routers import assets, condition


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Luxury AI Clienteling API — Backend",
    description=(
        "고객의 물건(상태)을 아는 럭셔리 AI 상담 서비스 Backend.\n\n"
        "**계약 엔드포인트** (docs/CONTRACTS.md):\n"
        "- `GET /assets/{customer_id}` — 고객 소유 개체 + 컨디션\n"
        "- `POST /fingerprint/match` — 개체 지문 매칭 (ORB CV)\n"
        "- `POST /condition/score` — 컨디션 점수 분석 (OpenCV)\n\n"
        "**연결**: `ASSET_ADAPTER=http ASSET_BASE_URL=http://localhost:8001 make dev`"
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — 개발 환경: 통합 레이어(:8000) + 프론트(:5173) 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 배포 시 실제 도메인으로 교체
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 계약 라우터 (백엔드 담당 엔드포인트) ─────────────────
app.include_router(assets.router)       # GET /assets/{customer_id}
app.include_router(condition.router)    # POST /condition/score
app.include_router(fingerprint.router)  # POST /fingerprint/match + POST /api/fingerprint

# ── 레거시 라우터 (기존 프론트/AI 연동) ─────────────────
app.include_router(products.router, prefix="/api")   # GET /api/products/{id}
app.include_router(chat.router)                      # POST /api/chat


@app.get("/api/health", tags=["System"])
async def health():
    """헬스체크 — 통합 레이어가 어댑터 상태 확인 시 호출."""
    return {
        "status": "ok",
        "service": "Luxury AI Clienteling Backend",
        "version": "2.0.0",
        "endpoints": {
            "assets": "GET /assets/{customer_id}",
            "fingerprint_match": "POST /fingerprint/match",
            "condition_score": "POST /condition/score",
            "chat": "POST /api/chat",
        },
    }
