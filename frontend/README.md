# Luxe Clienteling — Frontend

React + Vite + Tailwind CSS 4. 통합 레이어(`:8000`)의 API 를 그대로 쓰는 데모 화면이다.
의도적으로 빌드 툴체인을 최소화했다(vanilla JS + JSX, 상태 라이브러리 없음).

## 실행

```bash
npm ci
npm run dev      # http://localhost:5173 — /session 등 API 를 :8000 으로 프록시
npm run lint     # oxlint
npm run build    # dist/ (배포는 deploy/04_build_frontend.sh)
```

통합 레이어를 함께 띄워야 실데이터가 나온다: 레포 루트에서 `make dev`.
서버가 없으면 **오프라인 목업으로 조용히 폴백**한다(아래 폴백 정책).

## 화면

| 경로 | 화면 | 부르는 API |
|---|---|---|
| `/` | 데모 시나리오 3종 재생 | `/demo/scenarios`, `/demo/scenarios/{id}/run` |
| `/consult` | 임의 고객·상품 직접 상담 | `/customers`, `/catalog`, `/session/advise` |
| `/result` | 상담 결과 (인용 카드 + AI 판단 과정 trace) | — (state 로 전달) |
| `/chat` | 자유 상담 챗봇 (선제 오프닝 포함) | `/assets/{id}`, `/intent/classify`, `/clienteling/reply`, `/clienteling/outreach` |
| `/identify` | 개체 지문 식별 → 고객 역추적 → 상담 연결 | `/demo/fingerprint-samples`, `/fingerprint/match` |

`/identify` 는 API 프록시 prefix(`/fingerprint`)와 겹치지 않도록 페이지 경로를 분리한 것이다
— 새 페이지를 추가할 때도 `vite.config.js` 프록시 목록·nginx location 정규식과 겹치지 않는
경로를 쓴다.

## 폴백 정책 (`src/api/client.js`)

- **fetch 자체가 실패**(서버 미기동·타임아웃·502~504)했을 때만 `src/api/mockData.js` 의
  오프라인 목업으로 조용히 폴백하고 헤더 배지를 "목업 모드"로 바꾼다.
- 서버가 응답한 4xx/유효성 에러는 목업으로 덮지 않고 화면에 그대로 보여준다.
- 목업 데이터는 **실제 서버 응답을 그대로 옮긴 것**이다 — 픽스처를 고치면 목업도
  실응답 기준으로 다시 맞춘다(값을 손으로 지어내지 않는다).

## 디자인 시스템

- 느와르 골드 다크 기본 + 아이보리 라이트(`data-theme`), 토큰은 `src/index.css` 의 CSS 변수.
- 서체는 전부 **셀프 호스팅**(`src/assets/fonts/`) — 발표장 네트워크가 끊겨도 로드돼야 한다.
  CDN 폰트·외부 리소스를 추가하지 않는다.
- 빌드 산출물 폴더는 `static-files/` 다(`vite.config.js` `assetsDir`) — 기본값 `assets/` 는
  nginx 의 API 프록시 경로 `/assets` 와 충돌한다.
