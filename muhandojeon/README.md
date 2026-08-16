# MCM Continuum

> 고객을 아는 AI가 아니라, 고객의 물건을 아는 AI.

제품 고유의 미세 텍스처(가죽 결·스티치)를 지문으로 등록해, AI가 고객이 실제 소유한 물건과 그 물리적 상태를 알고 상담하는 MCM 클라이언텔링 서비스입니다.

## 팀 역할

| 역할 | 인원 | 핵심 담당 | 폴더 |
|---|---|---|---|
| AI 1 — 고객 분석/Intent | 1명 | 고객 망설임 유형 분류, 페르소나, Intent Sensing | `ai/intent/` |
| AI 2 — Clienteling/LLM | 1명 | 상담 AI, 상품·브랜드 데이터 RAG, 개인화 답변 | `ai/clienteling/` |
| 기획·디자인 | 1명 | 문제정의, UX/UI, 고객 여정, 브랜드 톤, 발표자료 | `docs/` |
| 풀스택 1 — Frontend | 1명 | 고객용 웹/앱 UI, 상담 화면, 제품 화면 | `frontend/` |
| 풀스택 2 — Backend | 1명 | API, DB, 고객·상품·상담 데이터, AI 연동 | `backend/` |
| 풀스택 3 — Demo/Integration | 1명 | 전체 기능 통합, Persona Bot Lab, 배포·데모 안정화 | `demo/` |

## 폴더 구조

```
mcm-continuum/
├── frontend/     # React + Vite — 고객용 웹 UI (촬영/상담/제품화면)
├── backend/      # API 서버, DB, AI 연동 오케스트레이션
├── ai/
│   ├── intent/       # 고객 분석 · Intent Sensing 모델/로직
│   └── clienteling/  # 상담 AI · RAG 파이프라인
├── docs/         # 문제정의, 기획 문서, 브랜드 가이드, 발표자료
└── demo/         # Persona Bot Lab, 통합 배포 스크립트
```

## 빠른 시작

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## API 연동 컨벤션 (확정 후 갱신)

- 백엔드 스택: FastAPI (확정)
- 베이스 URL: 개발 시 `http://localhost:8000` (프론트 프록시 기본값, `frontend/vite.config.js`에서 수정)
- 응답 포맷: 일반 JSON vs 스트리밍(SSE) — AI2 담당과 확정 필요
- CORS 허용 오리진: `http://localhost:5173` (프론트 개발 서버)

## 브랜치 컨벤션 (제안)

- `main`: 데모/제출용 안정 버전
- `feat/<이름>-<기능>`: 각자 작업 브랜치, 예) `feat/frontend-capture-screen`
- PR로 `main`에 머지 (8일 스프린트라 리뷰는 가볍게, 깨지는 것만 방지)
