"""AI1 인텐트 분류 서버 — 노트북 로직(intent_logic.py)의 얇은 HTTP 래퍼.

실행: uvicorn api:app --port 8101   (이 디렉토리에서)
통합 연결: INTENT_ADAPTER=http (INTENT_BASE_URL 기본값이 이미 :8101)

이 파일은 서빙 계층만 담당한다 — 분류 로직은 전부 intent_logic.py(노트북 5절 승격)에
있고 여기서는 한 줄도 다시 구현하지 않는다. 카탈로그는 있으면 로드해 정확도를 높이고
(동일 카테고리 반복 조회 신호), 없어도 동작한다(노트북과 같은 폴백).
"""

import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException

from intent_logic import predict_intent

logger = logging.getLogger("ai1.server")

# 통합 레포 루트의 시드 카탈로그 (AI/server/ 기준 두 단계 위). 없으면 catalog 신호만 건너뛴다.
_CATALOG_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "products.json"


def _load_catalog() -> dict:
    """{product_id: {category, price_krw}} — intent_logic.extract_signals 의 catalog 형식."""
    if not _CATALOG_PATH.exists():
        logger.warning("카탈로그 없음(%s) — 동일 카테고리 신호는 건너뛴다", _CATALOG_PATH)
        return {}
    raw = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    products = raw.get("products", raw) if isinstance(raw, dict) else raw
    return {
        p["product_id"]: {"category": p.get("category"), "price_krw": p.get("price_krw")}
        for p in products
        if p.get("product_id")
    }


CATALOG = _load_catalog()

app = FastAPI(
    title="AI1 — 구매 망설임 분류",
    description="세션 이벤트 시퀀스로 망설임 유형 5종을 분류한다 (docs/CONTRACTS.md).",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "AI1 intent classify",
        "source": "AI/AI1_intent_classify.ipynb 5절 (규칙 기반 신호 모델)",
        "catalog_products": len(CATALOG),
    }


@app.post("/intent/classify")
def intent_classify(request: dict) -> dict:
    """IntentClassifyRequest → IntentClassifyResponse (검증·분류 모두 intent_logic 소관)."""
    try:
        return predict_intent(request, catalog=CATALOG)
    except ValueError as exc:
        # 형식 위반(customer_id 누락 등) — 라벨 불확실과 달리 이것은 요청 오류다.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
