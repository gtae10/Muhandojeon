from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import products, fingerprint, chat

app = FastAPI(title="MCM Continuum API")

# 프론트 개발 서버(Vite) 오리진 허용 — 배포 시 실제 도메인으로 교체
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(fingerprint.router, prefix="/api/fingerprint", tags=["fingerprint"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
