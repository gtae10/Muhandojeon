# AI1 인텐트 분류 서버 (:8101)

`AI1_intent_classify.ipynb` 5절(POST /intent/classify 계약 구현)을 그대로 서버로 승격한 것.
분류 로직은 `intent_logic.py`(노트북 원문, **여기서 수정 금지** — 노트북에서 고치고 재반영),
서빙 계층은 `api.py`(FastAPI 래퍼) 뿐이다. ML 런타임 불필요 — 순수 파이썬 규칙 신호 모델.

## 실행

```bash
cd AI/server
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn api:app --port 8101
```

검증 (노트북 셀 5-6·5-7 재현 — 계약 예시 완전 일치 + 라벨 5종):

```bash
.venv/bin/pip install pytest && .venv/bin/python -m pytest test_contract.py -q
```

## 통합 레이어 연결

`INTENT_BASE_URL` 기본값이 이미 `http://localhost:8101` 이라 어댑터 전환 한 줄이면 된다:

```bash
INTENT_ADAPTER=http make dev
```

카탈로그(`fixtures/products.json`)가 레포에 있으면 자동 로드해 '동일 카테고리 반복 조회'
신호까지 켜지고, 없으면 그 신호만 건너뛴다(노트북과 동일한 폴백).
