# Luxury AI Clienteling — Backend

> **풀스택 2 (백엔드) 담당 서버**
> 계약 엔드포인트 구현 + 레거시 호환 유지

---

## 🚀 빠른 시작

### 1. 환경 변수 설정
```bash
cp .env.example .env
# .env 파일을 열어 OPENAI_API_KEY 값을 실제 키로 교체
```

### 2. 의존성 설치
```bash
pip install -r requirements.txt
# OpenCV 포함 (opencv-python-headless)
```

### 3. 서버 실행
```bash
# 신형 앱 (계약 엔드포인트 포함) — 권장
uvicorn app.main:app --reload --port 8001

# 구형 앱 (DB 연동 방식)
uvicorn main:app --reload --port 8000
```

### 4. API 문서 확인
- Swagger UI: http://localhost:8001/docs
- ReDoc:      http://localhost:8001/redoc

---

## 📁 프로젝트 구조

```
backend/
├── app/                          # 신형 앱 (계약 호환, 픽스처 기반)
│   ├── main.py                   # FastAPI 진입점 (계약 + 레거시 라우터 등록)
│   ├── data/
│   │   └── fixture_provider.py   # fixtures/*.json 읽기 + 캐싱 (단일 데이터 경계)
│   ├── routers/
│   │   ├── assets.py             # GET /assets/{customer_id}  ← 계약 담당
│   │   ├── condition.py          # POST /condition/score      ← 계약 담당
│   │   ├── fingerprint.py        # POST /fingerprint/match    ← 계약 담당
│   │   │                         # POST /api/fingerprint      ← 레거시 유지
│   │   ├── chat.py               # POST /api/chat (cited_asset_ids+cta 포함)
│   │   └── products.py           # GET /api/products/{id}
│   ├── services/
│   │   ├── condition_service.py  # OpenCV 기반 컨디션 분석
│   │   ├── fingerprint_service.py # ORB 기반 지문 매칭
│   │   ├── clienteling_service.py # AI2 연동 (OpenAI GPT-4o)
│   │   └── intent_service.py     # AI1 연동 (목업)
│   └── schemas/
│       └── models.py             # 계약 + 레거시 Pydantic 스키마
│
├── main.py                       # 구형 앱 (SQLAlchemy DB 방식)
├── models.py                     # SQLAlchemy ORM 모델
├── database.py                   # 비동기 DB 엔진
├── schemas.py                    # 구형 스키마
├── ai_service.py                 # 구형 AI 서비스
├── routers/                      # 구형 라우터
│   ├── assets.py
│   ├── events.py
│   └── chat.py
├── etl/
│   ├── remap_data.py             # 데이터 리매핑 (CSV 생성)
│   └── seed_db.py                # CSV → SQLite 로딩
└── requirements.txt
```

---

## 🔌 계약 엔드포인트 (백엔드 담당)

### `GET /assets/{customer_id}`

고객 소유 개체 목록 + 컨디션 반환.

**데이터 소스**: `fixtures/assets.json` + `fixtures/products.json` (픽스처 기반)
**정렬**: 오케스트레이터가 담당 → 백엔드는 정렬 안 함

```json
{
  "customer_id": "CU-0001",
  "tier": "VIP",
  "assets": [
    {
      "asset_id": "AS-0001",
      "product_name": "Aurelia Top Handle",
      "category": "BAG",
      "condition_score": 71,
      "findings": [
        { "part": "handle", "severity": "MEDIUM", "note": "핸들 표면 마모 진행" }
      ],
      "next_service_months": 1
    }
  ]
}
```

---

### `POST /fingerprint/match`

촬영 이미지를 등록 개체와 대조.

**매칭 방법**: OpenCV ORB 특징점 + BFMatcher(NORM_HAMMING)  
**등록 이미지 경로**: `data/fingerprints/{asset_id}/{angle}_{index}.jpg`  
**임계값**: 0.75 (docs/CONTRACTS.md)

```json
// 요청
{ "image_path": "data/fingerprints/AS-0001/handle_01.jpg", "customer_id": "CU-0001", "top_k": 3 }

// 응답
{ "matched_asset_id": "AS-0001", "similarity": 0.91, "is_match": true, "candidates": [...], "threshold": 0.75 }
```

---

### `POST /condition/score`

개체 컨디션 점수 + 부위별 소견.

**이미지 있음**: OpenCV ORB/Canny 기반 마모도 분석  
**이미지 없음**: `fixtures/assets.json` 마지막 스캔 결과 반환  
**케어 임계값**: 70점 (docs/CONTRACTS.md)

```json
// 요청
{ "asset_id": "AS-0001", "image_paths": [] }

// 응답
{ "asset_id": "AS-0001", "score": 71, "findings": [...], "next_service_months": 1, "confidence": 0.8 }
```

---

### `POST /api/chat` (계약 호환 확장)

**변경**: 응답에 `cited_asset_ids` + `cta` 필드 추가 (docs/BACKEND_INTEGRATION.md 필수)

```json
{
  "session_id": "s1",
  "reply": "고객님의 AS-0001 Aurelia Top Handle 핸들 마모...",
  "model_used": "gpt-4o",
  "cited_asset_ids": ["AS-0001"],
  "cta": "CARE_BOOKING"
}
```

---

## 🔗 통합 레이어 연결

```bash
# 자산 조회만 실제 백엔드로
ASSET_ADAPTER=http ASSET_BASE_URL=http://localhost:8001 make dev

# 컨디션 분석까지
CONDITION_ADAPTER=http CONDITION_BASE_URL=http://localhost:8001 make dev

# 상담까지 (AI2)
CLIENTELING_ADAPTER=http CLIENTELING_BASE_URL=http://localhost:8001 make dev
```

상태 확인:
```bash
curl -s localhost:8000/health/detail | jq '.adapters'
# mode: "http", last_status: "ok" 또는 "ok(legacy-mapped)"
```

---

## 📦 레거시 필드 매핑

| 계약 필드 | 백엔드 레거시 필드 | 변환 |
|---|---|---|
| `customer_id` | `user_id` | 동일 처리 |
| `purchased_at` | `purchase_date` | ISO 형식 그대로 |
| `last_scanned_at` | `last_assessed` | ISO 형식 그대로 |
| `tier` | (없음) | 개체 수로 추정 (8+→VIP / 3~7→ESTABLISHED / 그 외→NEW) |
| `next_service_months` | (없음) | 70점 도달까지 연 8점 감소 가정 계산 |
| `message` | `reply` | 동일 처리 |

---

## 🤖 OpenCV 컨디션 분석

비전 API(LLM)는 사용하지 않는다 (docs/INTEGRATION.md 확정 제약).
고전 CV 파이프라인:

```
이미지 → ORB 특징점 추출 → 텍스처 복잡도(마모 지표)
       → Canny 엣지 감지 → 스크래치/균열 밀도
       → 밝기 표준편차 → 색 바램 지표
       → 가중 합산 → score(0~100)
```

`pip install opencv-python-headless` 로 설치. 미설치 시 픽스처 데이터로 폴백.
