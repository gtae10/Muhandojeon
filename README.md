# Luxe Clienteling — 통합/데모 레이어

럭셔리 브랜드용 AI 클라이언텔링 서비스의 **통합/데모 담당** 코드베이스.
"고객을 아는 AI" 가 아니라 **"고객의 물건을 아는 AI"** 라는 것이 이 제품의 차별점이고,
그 차별점이 실제로 작동하는지를 이 레이어가 측정한다(상담이 소유 자산을 인용하지 않으면
`owned_assets_used=false` 로 드러난다).

- 계약(팀 인터페이스): [`docs/CONTRACTS.md`](docs/CONTRACTS.md)
- 데이터 출처·한계: [`docs/DATA_PROVENANCE.md`](docs/DATA_PROVENANCE.md)
- 라이선스: [`docs/DATA_LICENSES.md`](docs/DATA_LICENSES.md)
- 기존 백엔드 연동: [`docs/BACKEND_INTEGRATION.md`](docs/BACKEND_INTEGRATION.md)
- 개체 지문 촬영: [`docs/FINGERPRINT_CAPTURE.md`](docs/FINGERPRINT_CAPTURE.md)
- 데모 당일 체크리스트: [`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md)

## 1. 실행 방법

```bash
make setup          # uv venv(3.11) + 의존성 + .env 생성
make data           # 데이터 획득 → 정규화 → export → SQLite (없으면 synth 폴백)
make dev            # 목 모드 서버 :8000
```

확인:

```bash
curl -s localhost:8000/health/detail | jq          # 발표 직전 5초 점검
open http://localhost:8000/docs                    # OpenAPI
open http://localhost:8000/lab                     # Persona Bot Lab 대시보드
```

전체 타깃:

| 명령 | 설명 |
|---|---|
| `make setup` | venv + 의존성 설치 |
| `make data` | 데이터 파이프라인 전체 (fetch → build → export → provenance → seed) |
| `make data-synth` | 외부 데이터 무시하고 합성만으로 완주 |
| `make dev` | 목 모드 개발 서버 (reload) |
| `make demo` | 데모 모드 (LLM 디스크 캐시 + 캐시 워밍업 후 기동) |
| `make lab` | Persona Bot Lab 45세션 CLI 실행 |
| `make check` | ruff + mypy + 헬스체크 + 데모 시나리오 검증 |
| `make demo-check` | 데모 시나리오 3종만 검증(문구 전문 출력) |
| `make test` | pytest |
| `make contracts` / `make docs` | 계약·출처 문서 재생성 |
| `make clean-db` / `make clean-cache` | SQLite / LLM 캐시 삭제 |

스크립트는 프로젝트 루트에서 `python -m scripts.<name>` 으로 실행한다
(편집 설치 `.pth` 가 환경에 따라 `sys.path` 에 안 잡히는 문제를 우회한다).

## 2. 데이터셋 준비

### Kaggle 인증

```bash
pip install kaggle
# https://www.kaggle.com/settings → API → Create New Token → kaggle.json 다운로드
mkdir -p ~/.kaggle && mv ~/Downloads/kaggle.json ~/.kaggle/ && chmod 600 ~/.kaggle/kaggle.json
python -m scripts.fetch_data
```

### H&M 은 대회 규칙 수락이 필요하다 (현재 미수락 → 합성 폴백 중)

`transactions_train.csv` 는 competition 데이터라 **웹에서 규칙에 동의하지 않으면 API 다운로드가
403** 이다(파일 목록 조회는 되지만 다운로드가 막힌다).

```
https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/rules
→ "I Understand and Accept" → make data 재실행
```

동의 전에도 파이프라인은 완주한다. 고객·거래 슬라이스만 합성으로 채워지고, 그 사실이
`data/processed/provenance.json` 과 `docs/DATA_PROVENANCE.md` 에 기록된다.

### 수동 다운로드 / 다른 경로에 둔 파일

```bash
# 원본을 다른 디스크에 뒀다면 env 로 가리킨다
HM_TRANSACTIONS_PATH=/mnt/data/transactions_train.csv make data
STYLES_CSV_PATH=... FASHION_IMAGES_PATH=... CLICKSTREAM_CSV_PATH=... make data
```

MVTec AD 는 **CC BY-NC-SA 4.0(상업적 사용 금지)** 이라 자동 다운로드하지 않는다.
`data/raw/mvtec/` 에 직접 놓으면 인식하고, 없으면 조용히 건너뛴다.

### 합성 폴백만으로 돌리기

```bash
make data-synth                      # 상품 40 / 고객 30 / 세션 60 전부 합성
python -m scripts.synth_fallback --dry-run
```

## 3. 팀원별 전달 사항

전부 `exports/` 에 있고 스키마는 [`exports/README.md`](exports/README.md) 에 있다.
필드명은 `contracts/` 의 Pydantic 모델과 맞춰져 있으니 파이썬이면 그대로 import 해서 검증하는 편이 안전하다.

### AI1 — 인텐트/망설임 분류

- **파일**: `exports/intent_trainset.parquet` (60행, `split` 컬럼으로 train/val 8:2 계층 분할)
- **할 일**: `POST /intent/classify` 구현. 입출력은 `docs/CONTRACTS.md` 그대로.
- **입력 그대로 쓰기**: `events_json` 컬럼이 계약의 `SessionEvent[]` 다. 그대로 모델 입력으로 쓸 수 있다.
- **반드시 읽을 것**: 라벨은 사람이 아니라 규칙(`app/intent_rules.py`)이 만들었다. 규칙을 외우면
  val 정확도가 1.0 에 가까워지는데 그건 성능이 아니라 누수다. 규칙이 쓰지 않는 신호(체류 분포,
  순서 패턴)로 일반화하는지 함께 보고해 달라. 60행은 적으니 `build_sessions.py --force` 로
  세션 수를 늘려 증강하는 편이 스키마 안전하다.
- **비교 기준선**: 지금 목 어댑터가 그 규칙 엔진이다. 즉 "규칙 대비 개선" 을 같은 기준으로 잴 수 있다.

### AI2 — 클라이언텔링 상담

- **파일**: `exports/catalog_rag.jsonl` (상품 40개 문서, `{id, text, metadata}` — 벡터 스토어에 바로 투입),
  `exports/customer_context.json` (고객 30명 × 소유 자산 + 컨디션 + `priority_asset_ids`)
- **할 일**: `POST /clienteling/reply` 구현.
- **하드 요구사항**: `owned_assets` 가 비어 있지 않으면 **`cited_asset_ids` 를 반드시 채운다.**
  비면 오케스트레이터가 `owned_assets_used=false` 로 표시하고 경고 로그를 남긴다(제품 실패 신호).
  Persona Bot Lab 의 전략 S2 는 인용 여부로 평가되므로, 이 필드가 없으면 S2 효과가 0으로 측정된다.
- **인용 순서**: `priority_asset_ids` 가 인용 우선순위다(컨디션 낮음/케어 임박/동일 카테고리 순).
- **문장 예시**: 지금 목 응답이 기준선이다. `python -m scripts.check_demo --verbose` 로 3종 시나리오 문구를 볼 수 있다.

### 백엔드 — 개체 지문 / 컨디션 / 자산

- **할 일**: `POST /fingerprint/match`, `POST /condition/score`, `GET /assets/{customer_id}`
- **이미 만든 API 와의 차이**: [`docs/BACKEND_INTEGRATION.md`](docs/BACKEND_INTEGRATION.md) 에 필드
  대응표가 있다. 통합 레이어가 레거시 스키마(`user_id`/`purchase_date`/`wear_details`/`reply`)를
  자동 매핑하므로 **백엔드를 고치지 않아도 붙는다.** 단 `cited_asset_ids` 는 예외(위 참고).
- **지문 임베딩 대상 목록**: `sqlite3 data/app.db "select asset_id, angle, path from fingerprints where passed=1"`
  — 품질 검증(해상도/블러/밝기/과노출)은 `scripts/register_fingerprint.py` 가 이미 끝냈다.
- **촬영 규약**: `docs/FINGERPRINT_CAPTURE.md`

### 프론트

- **단일 진입점**: `POST /session/advise` → `docs/CONTRACTS.md` 의 `AdviseResponse` 하나만 렌더하면 된다.
- 화면 채우기용 읽기 전용: `GET /catalog`, `GET /catalog/{id}`, `GET /customers`, `GET /sessions`,
  `GET /sessions/{id}`, 이미지는 `/static/images/{product_id}.jpg` (원본 60x80 — 작게 렌더할 것)
- 응답 헤더 `X-Degraded`, `X-Owned-Assets-Used` 를 보면 폴백 여부와 차별점 작동 여부를 알 수 있다.
- CORS 는 전면 허용(`*`)이다.

## 4. 목 → 실제 전환

모듈별로 하나씩 켠다. 전역 `ADAPTER_MODE=http` 는 전부 켜므로 마지막에 쓴다.

```bash
# 인텐트만 실제 AI1 서버로
INTENT_ADAPTER=http INTENT_BASE_URL=http://localhost:8101 make dev

# 자산 + 상담을 팀 백엔드로 (같은 서버여도 무관)
ASSET_ADAPTER=http CLIENTELING_ADAPTER=http \
  ASSET_BASE_URL=http://localhost:8000 CLIENTELING_BASE_URL=http://localhost:8000 make dev

# 전부 실제
ADAPTER_MODE=http make dev
```

| env | 값 | 기본 |
|---|---|---|
| `ADAPTER_MODE` | `mock` / `http` | `mock` |
| `INTENT_ADAPTER` / `CLIENTELING_ADAPTER` / `ASSET_ADAPTER` / `FINGERPRINT_ADAPTER` / `CONDITION_ADAPTER` | `mock` / `http` (전역보다 우선) | 미설정 |
| `*_BASE_URL` | 각 모듈 업스트림 | `localhost:8101~8105` |
| `UPSTREAM_TIMEOUT_SECONDS` / `UPSTREAM_RETRIES` | 타임아웃/재시도 | `5.0` / `1` |

전환 확인:

```bash
curl -s localhost:8000/health/detail | jq '.adapters'
# mode 가 http 이고 last_status 가 ok 또는 ok(legacy-mapped) 인지 본다.
```

업스트림이 죽어도 `/session/advise` 는 **200 + `X-Degraded: true`** 로 응답하고 규칙/템플릿
폴백 문구를 돌려준다(발표 중 에러 화면 금지). 어느 단계가 폴백됐는지는 응답 `trace` 에 있다.

## 5. LLM 연결

OpenAI 호환 엔드포인트만 쓴다(로컬 vLLM / 상용 API 모두 동일).

```bash
LLM_BASE_URL=http://localhost:8000/v1 LLM_MODEL=qwen2.5-7b-instruct LLM_API_KEY=dummy make dev
LLM_BASE_URL=https://api.openai.com/v1 LLM_MODEL=gpt-4o-mini LLM_API_KEY=sk-... make demo
```

- 키가 없으면 **결정적 템플릿 폴백**으로 동작한다(크래시하지 않는다). 상담 문구·페르소나 봇·심판
  모두 규칙 모델로 돌아가며, 그 사실이 `/lab` 대시보드와 `/health/detail` 에 표시된다.
- `DEMO_MODE=true` 면 모든 LLM 응답이 `.cache/llm/` 에 캐시되고 동일 입력은 캐시에서 반환된다
  (네트워크가 끊겨도 워밍업된 시나리오는 그대로 돌아간다).

## 6. 구조

```
contracts/        팀 전체 인터페이스(Pydantic v2) — 단일 출처. docs/CONTRACTS.md 는 여기서 생성
app/
  adapters/       모듈별 Mock/Http 어댑터 + 레지스트리(전환 지점)
  services/       오케스트레이터(5단계 플로우 + 인용 검증)
  lab/            Persona Bot Lab (고객 봇 / 심판 / 러너 / 대시보드)
  intent_rules.py 망설임 분류 규칙 — 학습셋 라벨과 목 응답이 공유
  clienteling_rules.py  상담 문구 조립 규칙(LLM 폴백 겸 기준선)
  domain.py       컨디션 계산·소견·럭셔리 어휘(모두 결정적)
scripts/          데이터 파이프라인 + 문서 생성기 + Lab/데모 CLI
data/processed/   정규화 산출물(사실의 원본). SQLite 는 조회용 사본
exports/          팀원 배포용 (AI1 학습셋 / AI2 RAG·컨텍스트)
```

## 7. 재현성 규칙 (깨면 데모가 깨진다)

- 모든 샘플링·분할은 `seed=42`. 난수 대신 `sha1` 기반 결정적 선택을 쓴다.
- 기준시각은 `REFERENCE_NOW = 2026-08-14T12:00:00+09:00` 고정. 컨디션이 경과 연수 함수라
  `now()` 를 쓰면 "컨디션 71점" 대사가 매일 흔들린다.
- `data/processed/catalog_luxury.json` 은 `--force` 없이 재생성하지 않는다(상품명 = 발표 대본).
- 데모 시나리오는 고객·상품·전략·세션을 id 로 못박는다. `make demo-check` 로 기대값을 검증한다.
