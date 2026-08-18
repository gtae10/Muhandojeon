# MCM 클라이언텔링 AI — 상담 에이전트 (AI 2 파트)

고객이 **이미 가진 물건**을 아는 에이전트입니다.
구매 이력을 추측해 새 제품을 권하는 대신, 보유 제품의 상태를 근거로
케어와 수선을 먼저 제안합니다.

---

## 실행하기

### 1. 코드 받기

```bash
git clone <저장소 주소>
cd ai-clienteling        # 팀 통합 저장소(Muhandojeon)라면 Muhandojeon/ai-clienteling
```

### 2. 라이브러리 설치

```bash
pip install -r requirements.txt
```

### 3. API 키 넣기

`.env` 파일은 **저장소에 올라가지 않습니다.** 각자 만들어야 합니다.

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

만든 `.env` 를 열어서 `OPENAI_API_KEY` 에 실제 키를 넣습니다.
키는 저장소가 아닌 다른 경로로 전달받으세요.

```
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4o
```

데모는 `gpt-4o` 입니다 (2026-08-18 전환 — 긴 대화에서 mini 가 대화를 놓치는
경우가 있어 실측 후 바꿨습니다). 개발·회귀를 싸게 돌릴 때는 `gpt-4o-mini` 를
쓰세요 (비용 약 1/20). 프롬프트를 고쳤다면 두 모델 다 돌려야 합니다.

### 4. 실행

```bash
python agent.py           # 콘솔에서 대화 (개발용)
python agent.py --demo    # 시연용 — 내부 표시를 숨긴다
```

고객 ID를 넣으면 **에이전트가 먼저 말을 겁니다.** `quit` 으로 종료합니다.

### 어느 ID를 넣어야 하나

10명은 숫자를 채운 것이 아니라 **검증할 상황이 10가지**여서입니다.
무엇을 보고 싶은지에 따라 고르세요.

| ID | 상황 | 여기서 보이는 것 |
|---|---|---|
| **C001** | 도쿄 출장 중, 긴자에서 착장 후 미구매 | **히어로.** 먼저 말 걸기 → 망설임 해소 → 케어 제안 → 출처 추궁 |
| C002 | 온라인 장바구니에 담고 이탈 | 담아두신 것을 꺼내며 무엇이 걸렸는지 묻기 |
| C003 | 국내 매장에서 착장 후 미구매 | 국내 배송·픽업 경로 |
| C004 | 도쿄 매장에 원하는 색이 없었음 | 옴니채널 — 타 매장 재고, 귀국 후 수령 |
| C005 | 온라인에서 반복 조회 | 조회 기록을 말하지 않으면서 대화 열기 |
| C006 | 3년 전 케어 이력 있음 | 지난 케어를 관계로 꺼내기 |
| C007 | 부산 거주 | 아는 도시는 매장 이름을, 모르는 도시는 확인 제안 |
| C008 | 싱가포르 거주 · 영어 | 다국어 — 응답 언어를 코드가 정함 |
| C009 | 결제 완료, 수령 방법 미정 | 배송/픽업 안내 (`delivery` 액션) |
| C010 | 보유 3점 · 7년 사용 제품 | 교체 요구를 케어로 받기, 어느 제품인지 되묻기 |

시연에서 보여줄 네 대화는 `tests/test_rehearsal.py` 에 그대로 들어 있습니다
(C001 · C006 · C010 · C007). 왜 이 10가지인지는 [DESIGN.md](DESIGN.md) 1절에 있습니다.

---

## API 서버

```bash
uvicorn api:app --reload --port 8102
```

문서: <http://localhost:8102/docs> (8102 는 통합 레이어의 포트 배정)

| 엔드포인트 | 용도 |
|---|---|
| `POST /chat` | 고객 발화에 응답 (팀 합의 스펙) |
| `POST /outreach` | 에이전트가 먼저 말 걸기 (**스펙 협의 필요**) |
| `POST /clienteling/reply` | **통합 레이어 계약 경로.** 한 메종 세계관(18종·16명)으로 응답, `cited_asset_ids`(근거 카드)·`cta` 포함 |
| `POST /clienteling/outreach` | 통합 세계관에서 먼저 말 걸기 — 계기 없으면 400 |
| `POST /api/chat` | 통합 레이어 폴백 경로 |
| `GET /preview` | **개발 확인용 화면** — 시나리오 14종 오프닝 + 자유 대화 + 근거 카드 재현 |
| `GET /health` | 서버·모델 확인 |

통합 경로의 세계관·인용 규칙·데이터 동기화는 [HANDOFF.md](HANDOFF.md) 12번에
정리되어 있습니다. 팀 fixtures 를 고치셨다면
`python scripts/build_integration_data.py` 한 번으로 반영됩니다.

### 입출력

```jsonc
// 요청
{
  "customer_id": "C001",
  "message": "고객 발화 텍스트",
  "conversation_history": [{"role": "user", "content": "..."}],

  // 우리 값과 팀 계약 라벨을 모두 받습니다. 변환하지 말고 그대로 넘기세요.
  //   우리 값    : fit | price | timing | comparison | null
  //   계약 라벨  : SIZE_UNCERTAIN | PRICE_HESITANT | STYLE_DOUBT | STOCK_CONCERN | NONE
  "hesitation_type": null,

  "owned_products": [ /* 생략 가능. 보내면 더미보다 우선한다 */ ]
}

// 응답
{
  "reply": "에이전트 답변 텍스트",
  "suggested_action": "care_booking | stock_hold | delivery | staff_connect | none"
}
```

**대화 기록은 부르는 쪽이 관리합니다.** 서버는 상태를 갖지 않습니다.
여러 고객을 동시에 상대해도 대화가 섞이지 않게 하기 위함입니다.

### Frontend 참고 사항

화면을 어떻게 구성할지는 Frontend 에서 정하실 일이라, 저희 쪽 설계 의도만
공유드립니다.

- `suggested_action` 은 문장이 아니라 **신호**로 설계했습니다. 카드나 버튼 같은
  형태로 표현되면 의도가 살아납니다 — 예: `staff_connect` 는 "매장 어드바이저
  연결 요청됨" 카드, `none` 은 말풍선만. 고객에게 보여줄 문장은 `reply` 하나를
  생각하고 만들었습니다.
- `/outreach` 가 400 을 돌려줄 때의 `detail` 은 개발자용 메시지입니다.
  고객 화면에는 노출되지 않는 편이 안전합니다 — 먼저 말 걸 계기가 없을 때는
  아무것도 띄우지 않는 것을 의도한 설계라서요.

---

## 폴더 구조

```
agent.py            콘솔 대화 (개발·시연용)
api.py              FastAPI 서버 (통합 연동 경로 포함)
engine.py           응답 생성. 상태를 갖지 않는다
integration.py      [미사용 폴백] 폐기된 이전 통합 모드 — docstring 에 사유
preview.html        /preview 개발 확인 화면 (시나리오 캐스트 + 근거 카드 재현)
prompts/
  system_prompt.py  시스템 프롬프트 + 응대 전략 4종
  knowledge.py      판단을 코드가 하는 부분 (매장·예산·기간·지역) + 데이터 오버레이
scripts/
  build_integration_data.py  팀 fixtures → 통합 데이터 재생성 (사본 금지)
data/
  products.json     제품 6종 (MCM — /chat 데모용, 동결)
  heritage.json     브랜드 헤리티지 9절
  services.json     케어·수선·배송 정책
  customers.json    더미 고객 10명
  stores.json       매장 5곳 (서울 3, 부산 1, 도쿄 1)
  regions.json      국가·도시 매핑
  integration_*.json  통합 경로 데이터 4종 — 스크립트 산출물, 직접 수정 금지
                      (카탈로그 18종 · 고객 16명 · 확장 재고 · 고객별 자산)
tests/              회귀 테스트 13종
```

---

## 테스트

```bash
python tests/test_rehearsal.py         # 발표용 네 대화를 이어서 돌린다
python tests/test_privacy.py           # 출처 추궁 — 절대 깨지면 안 되는 장면
python tests/test_variants.py          # 응대 전략 4종 비교 (대조군 포함)
python tests/test_overlay.py           # 통합 오버레이 격리 — /chat 동결 증명 (LLM 호출 0)
python tests/test_integration_mode.py  # 통합 경로 — 18종 인지·재고·인용 게이트
```

프롬프트를 고쳤다면 **반드시** 전체를 다시 돌리세요.
턴 단위 테스트만으로는 대화 품질을 보증할 수 없습니다.

---

## 데이터에 대해

모든 고객 데이터는 **가상**입니다. 실제 고객 데이터를 쓰지 않았습니다.

제품·매장·서비스 정보는 MCM 공식 자료를 직접 확인해 옮겼습니다.
자동 수집을 쓰지 않은 이유는 로케이터가 부정확하고 폐점·팝업이 섞여 있어서입니다.
실제로 부산 센텀시티점이 폐점인 것을 확인 과정에서 발견했습니다.

우리가 모르는 것은 지어내지 않습니다. 동시에 "없습니다"라고 단정하지도 않습니다.
매장 정보가 없는 지역은 확인 책임을 에이전트가 가져갑니다.
실서비스에서는 그 자리에 매장 조회 API가 들어옵니다.

**고객의 위치도 마찬가지입니다.** 프로필의 거주지는 등록된 지역이지 오늘 계신 곳이
아니라서, 매장에서의 접점이 있는 고객에게만 "지금 그곳에 계신다"고 말합니다.
나머지는 매장 이름은 그대로 대되 위치는 단정하지 않습니다.

되묻기도 우리가 지킬 수 있는 것만 합니다. "다른 지역이 편하시면 말씀해 주세요"는
매장 정보를 전부 가진 서비스만 할 수 있는 말이라 쓰지 않습니다.
고르시게 하는 것은 그 지역에 실제로 있는 매장 중에서입니다.

---

## 더 읽을 것

- **[HANDOFF.md](HANDOFF.md)** — **다른 파트에서 확인해 주셔야 하는 것들.**
  `/outreach` 연동, `suggested_action` 렌더링, 대화 기록 관리 주체,
  보유 제품을 목록으로 보내기, 접점의 `intentional` 필드 등.
  연동 전에 한 번 봐주세요.
- **[DESIGN.md](DESIGN.md)** — 왜 이렇게 만들었는가.
  더미 고객이 10명인 이유, 판단을 코드로 옮긴 이유, 개인화와 감시의 경계,
  **무엇을 말해도 되는가**(의도적 접점과 수동 관측), 검증 방식까지.
  **코드를 고치기 전에 읽어주세요.**
- `CLAUDE.md` — 개발 과정에서 실패한 사례와 그때 얻은 원칙. 분량이 많습니다.
