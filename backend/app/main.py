"""
app/main.py - FastAPI 앱 진입점
"""
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import products, fingerprint, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="Luxury AI Clienteling API",
    description="고객의 물건(상태)을 아는 럭셔리 AI 상담 서비스",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - 프론트(Vite 기본 포트) 허용
# 배포 시 실제 프론트 도메인 추가 필요
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(products.router, prefix="/api")
app.include_router(fingerprint.router, prefix="/api")
app.include_router(chat.router, prefix="/api")


@app.get("/api/health", tags=["System"])
async def health():
    return {"status": "ok", "service": "Luxury AI Clienteling Backend"}
