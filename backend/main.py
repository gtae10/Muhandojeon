"""
main.py - FastAPI Application Entry Point
Luxury AI Clienteling Service Backend
"""

from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()  # .env 파일 로드 (OPENAI_API_KEY 등)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_db
from routers import assets, events, chat


# ──────────────────────────────────────────────
# Lifespan (startup / shutdown)
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


# ──────────────────────────────────────────────
# App Factory
# ──────────────────────────────────────────────

app = FastAPI(
    title="Luxury AI Clienteling API",
    description="고객의 물건(상태)을 아는 초개인화 럭셔리 상담 서비스 Backend",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS (프론트엔드 연동용 - 개발 환경)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 배포 시 실제 도메인으로 교체
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Routers
# ──────────────────────────────────────────────

app.include_router(assets.router)
app.include_router(events.router)
app.include_router(chat.router)


# ──────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "Luxury AI Clienteling Backend"}


# ──────────────────────────────────────────────
# Dev Runner
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
