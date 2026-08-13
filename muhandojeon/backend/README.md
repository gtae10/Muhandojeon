# Backend

담당: 풀스택 2

## 스택
FastAPI (확정)

## 실행
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
`http://localhost:8000/docs`에서 Swagger로 API 바로 확인 가능

## 구조
```
backend/
├── requirements.txt
└── app/
    ├── main.py            # FastAPI 앱 진입점, CORS 설정
    ├── routers/
    │   ├── products.py     # GET /api/products/:id
    │   ├── fingerprint.py  # POST /api/fingerprint
    │   └── chat.py         # POST /api/chat
    ├── schemas/
    │   └── models.py       # Pydantic 스키마 (프론트 api/client.js와 필드 동일하게 맞춤)
    └── services/
        ├── intent_service.py       # AI1 연동 지점 (analyze_texture)
        └── clienteling_service.py  # AI2 연동 지점 (generate_reply)
```

## API

| 메서드 | 경로 | 설명 | 담당 |
|---|---|---|---|
| GET | `/api/health` | 헬스체크 | - |
| GET | `/api/products/{id}` | 제품 + 컨디션 정보 조회 | 백엔드(목업) |
| POST | `/api/fingerprint` | 이미지 업로드(`multipart/form-data`) → 지문 등록/상태 비교 | AI1 연동 |
| POST | `/api/chat` | 상담 메시지 전송 → 응답 | AI2 연동 |

현재 모든 엔드포인트는 목업 데이터로 동작 확인 완료 상태. `app/services/` 안의 두 함수만 실제 AI 로직으로 교체하면 됨.

## 확정 필요 (AI2 담당과 조율)
- 상담 응답을 일반 JSON으로 줄지, 스트리밍(SSE)으로 줄지
  - 스트리밍으로 가면 `routers/chat.py`를 `StreamingResponse`로, 프론트 `sendChatMessage`도 함께 수정 필요

## CORS
현재 `http://localhost:5173`(Vite 기본 포트)만 허용. 배포 시 실제 프론트 도메인 추가 필요 (`app/main.py`)
