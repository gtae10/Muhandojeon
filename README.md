# Luxury AI Clienteling — Backend

## 🚀 빠른 시작 (Quick Start)

### 1. 환경 변수 설정
```bash
cp .env.example .env
# .env 파일을 열어 OPENAI_API_KEY 값을 실제 키로 교체
```

### 2. 의존성 설치
```bash
pip install -r requirements.txt
```

### 3. ETL 실행 (CSV 데이터 생성)
```bash
python etl/remap_data.py
```

### 4. DB 시딩 (CSV → SQLite)
```bash
python etl/seed_db.py
```

### 5. 서버 실행
```bash
uvicorn main:app --reload --port 8000
# 또는
python main.py
```

### 6. API 문서 확인
- Swagger UI: http://localhost:8000/docs
- ReDoc:      http://localhost:8000/redoc

---

## 📁 프로젝트 구조

```
backend/
├── main.py              # FastAPI 앱 진입점
├── models.py            # SQLAlchemy ORM 모델 (5개 테이블)
├── database.py          # 비동기 DB 엔진 / 세션
├── schemas.py           # Pydantic 스키마 (요청/응답)
├── ai_service.py        # OpenAI API 연동 + 프롬프트 엔지니어링
├── requirements.txt
├── .env.example
├── routers/
│   ├── assets.py        # GET  /api/users/{user_id}/assets
│   ├── events.py        # POST /api/events/log
│   └── chat.py          # POST /api/chat/consult
└── etl/
    ├── remap_data.py    # 럭셔리 데이터 리매핑 (CSV 생성)
    └── seed_db.py       # CSV → SQLite 로딩
```

---

## 🗄️ DB 스키마 요약

| 테이블 | 역할 |
|---|---|
| `users` | 고객 정보 (이름, 등급: Bronze~Platinum, 국가) |
| `products` | 럭셔리 상품 카탈로그 (브랜드, 가격, 재질, 출시연도) |
| `assets` | 고객 소유 자산 + **컨디션 점수(1~100)** + 마모 세부 |
| `session_events` | 행동 로그 (view → add_to_cart → abandon 등) |
| `chat_histories` | AI 상담 대화 이력 (role: user/assistant/system) |

---

## 🔌 API 엔드포인트

### `GET /api/users/{user_id}/assets`
고객 소유 자산 + 컨디션 데이터 반환 (AI 2 RAG 인풋)

**Response 예시:**
```json
{
  "user_id": "abc-123",
  "total": 3,
  "assets": [
    {
      "product_name": "Neverfull MM",
      "brand": "Louis Vuitton",
      "category": "Bag",
      "condition_score": 72,
      "condition_grade": "Good",
      "wear_details": {
        "scratches": 4,
        "cracks": 0,
        "color_fade": false,
        "hardware_tarnish": true
      }
    }
  ]
}
```

---

### `POST /api/events/log`
프론트엔드 행동 이벤트 수집 (AI 1 망설임 분류용)

**Request 예시:**
```json
{
  "user_id": "abc-123",
  "session_id": "sess-xyz",
  "product_id": "prod-456",
  "event_type": "add_to_cart",
  "duration_sec": 45.2,
  "device": "mobile"
}
```

`event_type` 허용값: `view` | `add_to_cart` | `remove_from_cart` | `purchase` | `abandon`

---

### `POST /api/chat/consult`
AI 럭셔리 상담 (OpenAI GPT-4o 호출)

**Request 예시:**
```json
{
  "user_id": "abc-123",
  "session_id": "sess-xyz",
  "message": "네베풀 MM을 새로 사고 싶은데, 제 기존 가방이랑 너무 겹치지 않을까요?",
  "product_id": "prod-789",
  "include_cart": true
}
```

**Response 예시:**
```json
{
  "session_id": "sess-xyz",
  "reply": "고객님의 기존 네베풀 MM이 현재 Good 등급(72점)으로 하드웨어 변색이 시작되고 있습니다...",
  "model_used": "gpt-4o",
  "latency_ms": 1240,
  "assets_used": 3
}
```

---

## 🤖 AI 프롬프트 아키텍처

```
[System Prompt]
  └─ 고객 소유 자산 목록 + 컨디션 요약 (동적 주입)
  └─ 현재 관심 상품 컨텍스트
  └─ 럭셔리 어드바이저 페르소나 + 상담 원칙 5가지

[Messages]
  └─ 이전 대화 이력 (최대 10턴 = 20 메시지)
  └─ 현재 사용자 메시지

→ gpt-4o 호출 → DB 저장 → Response
```

---

## 🔧 PostgreSQL 전환 (운영 환경)

`.env` 파일에서 `DATABASE_URL`만 변경하면 됩니다:
```env
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/luxury_clienteling
```
`requirements.txt`의 `aiosqlite` → `asyncpg` 로 교체.
