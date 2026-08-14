# 인수인계 — 통합/데모 레이어를 이어받는 사람에게

이 문서만 읽고 작업을 이어갈 수 있게 쓴다. **"무엇을 고치려면 어디를 손대면 되는지"**를
작업 단위로 정리했다. 파트 전체 설명은 [`INTEGRATION.md`](INTEGRATION.md), 계약은
[`CONTRACTS.md`](CONTRACTS.md), 발표 당일 절차는 [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md).

---

## 0. 5분 온보딩

```bash
git clone <repo> && cd <repo>/            # 통합 레이어는 리포 루트에 있다
make setup                                # uv venv(3.11) + 의존성 + .env 생성
make check                                # ruff + mypy + 픽스처 검증 ← 여기가 통과해야 시작 가능
make dev                                  # :8000
```

브라우저로 확인:

| URL | 무엇 |
|---|---|
| `localhost:8000/health/detail` | 시드 소스·어댑터 모드·능력 플래그·예산·캐시 (5초 점검) |
| `localhost:8000/docs` | OpenAPI. 계약대로 구현됐는지 여기서 확인 |
| `localhost:8000/lab` | Persona Bot Lab 대시보드 (실행 전 비용 확인 다이얼로그) |
| `localhost:8000/ops` | 예산 게이지·용도별 비용·세션 1건당 원가 |

한 방에 상태 보기:

```bash
make verify        # check + pytest + 헬스체크 + 데모 시나리오 3종
make estimate      # 드라이런 비용 추정 (실제 LLM 호출 없음)
make demo-check    # 시나리오 문구 전문까지 출력
```

---

## 1. 이 파트가 담당하는 것 / 아닌 것

| 담당 | 비담당 (다른 팀원) |
|---|---|
| API 계약 정의(`contracts/`)와 문서 생성 | 인텐트 분류 모델 실구현 (AI1) |
| 시드 데이터(픽스처)와 provider 경계 | 상담 생성 모델 실구현 (AI2) |
| LLM 게이트웨이·예산 통제 | 개체 지문 임베딩 / 컨디션 CV (백엔드) |
| 오케스트레이터 + 목/HTTP 어댑터 | 프론트 화면 |
| Persona Bot Lab | |
| 데모 안정화(시나리오·폴백·캐시·헬스) | |

비담당 모듈은 **목으로 두고 계약만 정확히 맞춘다.** 팀원 모듈이 완성되면
`INTENT_ADAPTER=http` 처럼 모듈별로 하나씩 전환한다(코드 수정 없음).

---

## 2. 절대 전제 2개 (설계 판단의 뿌리)

### 비전(이미지 입력) 모델이 없다 — 확정

- 단일 출처: `config/llm_capabilities.json` 의 `"vision": false`. **런타임 탐지를 하지 않는다**
  (탐지 호출도 크레딧을 쓴다).
- **이미지를 프롬프트에 넣는 코드를 만들지 않는다.** 호출이 실패하면서 토큰만 태운다.
  `tests/test_budget.py::test_no_image_payload_in_any_prompt` 가 이를 고정한다.
- 컨디션 진단: 목(`MockConditionAdapter`)은 이미지를 보지 않고 `asset_id` 로 픽스처 값을 반환한다.
  실제 이미지 채점은 **백엔드가 고전 CV(OpenCV)로** 구현하며 계약은 불변이다
  (`CONDITION_ADAPTER=http` 로 전환).

### 크레딧 총액 100달러, 초과 시 복구 불가

- 3단 가드: 총 100 / 경고 60 / **하드 85**. 15달러는 발표 당일 재실행 여유분이다.
- 하드 리밋을 넘길 호출은 **실행 전에** 거부된다(사후 집계로는 늦다). 거부되면 캐시 또는
  결정적 템플릿으로 응답하므로 데모는 끊기지 않는다.
- 모든 호출은 `app/llm/` 게이트웨이를 지나며 `purpose=` 태그를 갖는다.

---

## 3. 코드 읽는 순서

```
1) contracts/                  팀 인터페이스(Pydantic v2). 여기가 계약의 단일 출처
2) app/data/provider.py        데이터 접근의 유일한 경계 (fixtures ↔ dataset 전환 지점)
3) app/services/orchestrator.py  /session/advise 5단계 + 인용 검증  ← 제품의 심장
4) app/adapters/registry.py    목 ↔ 실서버 전환 지점
5) app/llm/                    게이트웨이: client / budget / routing / pricing
6) app/lab/runner.py           Persona Bot Lab 시뮬레이션 루프
```

데이터 흐름:

```
fixtures/*.json
   └─ FixtureProvider (app/data/provider.py)   ← 픽스처를 직접 읽는 유일한 코드
        └─ DataStore (app/store.py)            ← 인메모리 캐시, 조회 편의
             ├─ Mock*Adapter (app/adapters/)
             ├─ Orchestrator (app/services/)   → POST /session/advise
             └─ Lab (app/lab/)                 → /lab

LLM 호출은 전부:  호출부 → app/llm/client.complete(purpose=...) → 라우팅 → 캐시 → 예산 게이트 → HTTP
                                                                          └→ llm_usage 테이블 기록
```

SQLite(`data/app.db`)에는 **런타임 산출물만** 있다: `lab_runs`, `lab_sessions`, `llm_usage`.
시드 데이터는 DB에 넣지 않는다(픽스처가 원본).

---

## 4. 작업 레시피

### A. 상품·고객·개체를 늘리거나 고치고 싶다

1. `fixtures/products.json` / `customers.json` / `assets.json` 편집
   - 상품: `last_code` 가 사이즈 체계다. **같은 `last_code` 면 치수 호환** → 사이즈 상담의 근거가 된다.
   - 상품: `stock_by_size` 의 합이 2 이하면 `is_scarce=true` 가 되어 S3(희소성) 문구의 사실 근거가 된다.
   - 개체: `product_name` 은 쓰지 않는다(provider 가 products 에서 조인해 채운다).
   - 개체: `findings[].part` 는 계약 열거형만 쓴다(handle/corner/hardware/stitching/lining/
     exterior/strap/sole/upper/edge_coat/dial/bracelet).
2. `make fixtures` → 스키마·참조·범위·데모 전제·라벨 도출·페르소나 바인딩까지 검사한다.
3. `make demo-check` → 시나리오 3종 문구가 여전히 기대값을 만족하는지 확인.

**건드리면 안 되는 3개** (검증이 막는다): `AS-0001` 컨디션 71점 + 핸들 마모 임계 근접(발표 핵심
대사), `AS-0016` 97점(대비용), `AS-0007` 54점(리세일 시나리오).

### B. 세션 시나리오를 추가하고 싶다

1. `fixtures/session_events.json` 에 시나리오 추가 — `scenario_id`, `label_hint`, `customer_id`,
   `target_product_id`, `events[]`(8~15개).
2. **라벨을 직접 적는 게 아니라** 이벤트 시퀀스가 그 라벨을 드러내야 한다. 규칙은
   `app/intent_rules.py` 에 있고 요약은 이렇다.
   - `SIZE_UNCERTAIN`: `size_guide` 2회 이상(서로 다른 사이즈면 가점)
   - `PRICE_HESITANT`: `price_filter_change`, 또는 `meta.cheaper_alternative=true` 조회
   - `STYLE_DOUBT`: 서로 다른 상품 4개 이상 + 총 체류 240초 이상
   - `STOCK_CONCERN`: `stock_check` / `shipping_info`
   - 공통: `add_to_cart` 후 결제 없음 → 이탈 가중
3. **타임스탬프는 고정값으로 쓴다.** 현재 시각을 넣으면 LLM 프롬프트 캐시가 매 실행 무효화되고
   예산이 샌다(`make cache-stats` 로 감시).
4. `make fixtures` 가 `label_hint` 와 규칙 도출 결과가 일치하는지 검사한다.

### C. 페르소나를 추가·수정하고 싶다

`data/personas.yaml` 편집. 필수: `customer_id`(픽스처에 존재 + 소유 개체 있음),
`target_product_id`, `initial_hesitation`, 파라미터 5개, `openings`(3개 권장).

파라미터 의미: `evidence_need`(내 물건 근거를 원하는 정도), `budget_sensitivity`,
`pressure_aversion`, `brand_familiarity`, `trust_threshold`(전환 임계 1~5), `patience_turns`.

`make fixtures` 가 바인딩·티어 요구(P1 개체 1개 / P4 60점 미만 보유 / P5 4개 이상)를 검사한다.
반복 회차는 초기 신뢰도 ±0.3 과 오프닝 변형만 다르다(결정적 시스템에서 같은 조건 N회는 무의미).

### D. 전략을 추가·수정하고 싶다

`data/strategies.yaml` 편집. **`cite_assets` 가 전략 간 핵심 차이**다(S2 만 true).
세 전략이 모두 자산을 인용하면 "자산 연계가 효과 있는가"를 측정할 수 없다.

새 전략을 추가하면 `app/clienteling_rules.py` 의 문장 조립에 반영될지 확인한다
(`scarcity_pressure >= 0.5` 면 희소성 문장이 앞에 붙는 식).

### E. 상담 문구를 고치고 싶다

두 경로가 있고 **둘 다 고쳐야** 일관된다.

| 경로 | 파일 | 언제 쓰이나 |
|---|---|---|
| 결정적 템플릿 | `app/clienteling_rules.py` | LLM 미연결/실패/예산 거부 시. 기준선 |
| LLM 프롬프트 | `app/adapters/clienteling.py::build_prompt` | LLM 연결 시 |

카테고리별 어휘 주의: `TRY_VERB`(가방=직접 들어 보고 / 신발=신어 보고), `SIZE_BASIS`
(신발=같은 라스트 계열 / 가방=같은 사이즈 체계). 여기를 틀리면 발표에서 바로 티가 난다.

수정 후: `make demo-check --verbose` 로 3종 문구 전문을 눈으로 확인한다.

### F. 새 LLM 호출을 추가하고 싶다 (중요)

```python
from app.llm import get_llm

text = get_llm().complete(
    messages,
    purpose="clienteling",        # ← 필수. 없으면 "other"(저가 티어)로 떨어진다
    fallback=lambda: "결정적 폴백 문구",   # ← 필수. 실패·거부 시 이 값이 나간다
    max_tokens=400,               # ← 상한을 조여라. 예산 게이트의 추정 정확도가 올라간다
    run_id=run_id,                # (선택) Lab 실행별 비용 집계용
)
```

새 용도를 쓰려면 `config/model_routing.yaml` 의 `purposes:` 에 티어를 등록한다.
JSON 응답이 필요하면 `complete_json(..., fallback=lambda: {...})` 을 쓴다(파싱 실패도 폴백으로 흡수).

지키면 되는 것: **예외를 던지지 않는다**(게이트웨이가 전부 흡수), **프롬프트에 현재 시각·UUID·
랜덤값을 넣지 않는다**(캐시 무효화 → 예산 사고), **이미지를 넣지 않는다**(비전 없음).

추가 후 확인:

```bash
make estimate                 # 호출 횟수·토큰·비용이 예상대로인지
make cache-stats --by-run     # 재실행 히트율 90% 이상인지
```

### G. 목을 실제 서버로 바꾸고 싶다

```bash
INTENT_ADAPTER=http INTENT_BASE_URL=http://localhost:8101 make dev   # 모듈별로 하나씩
ADAPTER_MODE=http make dev                                           # 전역(마지막에)
```

확인: `curl -s localhost:8000/health/detail | jq '.adapters'` → `mode: http`,
`last_status: ok` 또는 `ok(legacy-mapped)`.

`ok(legacy-mapped)` 는 팀 백엔드의 기존 필드명을 어댑터가 변환했다는 뜻이다(정상).
매핑표는 [`BACKEND_INTEGRATION.md`](BACKEND_INTEGRATION.md), 테스트는 `tests/test_legacy_mapping.py`.

업스트림이 죽어도 `/session/advise` 는 200 + `X-Degraded: true` 로 응답한다. 폴백 단계는
응답 `trace` 에 있다.

### H. 새 엔드포인트를 추가하고 싶다

1. 계약이 필요하면 `contracts/` 에 모델 추가 → `contracts/registry.py` 의 `ENDPOINTS` 에 등록
   → `make contracts` 로 `docs/CONTRACTS.md` 와 `contracts/examples/*.json` 재생성.
   **문서를 손으로 고치지 않는다**(생성물이다).
2. 라우터는 `app/routers/` 에 파일 추가 → `app/main.py` 의 `include_router` 에 등록.
3. 데이터가 필요하면 provider/store 를 경유한다(픽스처 직접 읽기 금지).

### I. 데모 시나리오를 바꾸고 싶다

`data/demo_scenarios.yaml` — 고객·상품·전략·세션을 **id 로 못박는다**(무작위 선택 금지).
`expect` 블록이 검증 대상이다: `hesitation_type`, `owned_assets_used`, `min_citations`,
`cta_in`, `must_include_asset_condition`.

```bash
make demo-check                  # 전부 PASS 여야 발표 가능
curl -s -X POST localhost:8000/demo/scenarios/D3/run | jq '.check'
```

### J. 데이터셋이 확정됐을 때

1. `app/data/provider.py` 의 `DatasetProvider` 5개 메서드 구현
   (`get_products` / `get_customers` / `get_assets` / `get_session_events` / `get_scenarios`)
2. `SEED_SOURCE=dataset` 으로 전환
3. `python -m scripts.validate_fixtures --provider dataset` 로 같은 검증 통과
4. 보류 코드 복원이 필요하면 [`scripts/_deferred/README.md`](../scripts/_deferred/README.md)
   (ruff/mypy 제외 목록에서 빼고 다시 통과시킨다)
5. `data/personas.yaml` / `data/demo_scenarios.yaml` 의 id 갱신

**오케스트레이터·어댑터·Lab·데모 코드는 수정하지 않는다.** provider 를 둔 이유가 그것이다.

### K. 예산 설정·단가를 갱신하고 싶다

- 리밋: `.env` 의 `LLM_BUDGET_TOTAL_USD` / `WARN` / `HARD`. **하드를 100으로 올리지 않는다.**
- 단가: `config/model_pricing.yaml`. **대회 API 실단가가 확정되면 여기를 먼저 고친다.**
  미등록 모델은 보수적 기본값(입력 $1/1M, 출력 $3/1M)으로 계산되고 `/ops` 에 `pricing_entry:
  default` 로 표시된다.
- 모델명: `.env` 의 `LLM_MODEL`(상위) / `LLM_MODEL_CHEAP`(저가). **저가를 비워 두면 절감이 0이 된다.**
- 환율: `USD_KRW`(고정값, 실시간 조회하지 않는다).

---

## 5. 검증 명령이 각각 무엇을 보장하는가

| 명령 | 보장하는 것 |
|---|---|
| `make check` | 린트·타입 + 픽스처(스키마/참조/데모 전제/라벨 도출/페르소나 바인딩) |
| `make test` | 68개 테스트: 계약 매핑, 인용 검증, 예산 게이트, 캐시 히트율, 프롬프트 결정성 |
| `make healthcheck` | 서버 없이 in-process 로 실제 엔드포인트 호출(카탈로그·고객·Lab·데모·advise) |
| `make demo-check` | 시나리오 3종이 기대 라벨·인용·CTA·71점 인용을 만족 |
| `make estimate` | Lab 1회/시나리오 예상 비용, 티어 분리 효과, 잔여 실행 횟수 |
| `make cache-stats --by-run` | 재실행 히트율(90% 미만이면 프롬프트에 비결정적 값) |
| `make verify` | 위의 check + test + healthcheck + demo-check 한 번에 |

특히 이 세 테스트는 **제품 정의를 지키는 장치**라 실패하면 무시하지 말 것.

- `tests/test_orchestrator.py::test_hallucinated_citation_is_dropped` — 소유하지 않은 개체 인용 제거
- `tests/test_lab.py::test_judge_and_persona_bot_never_see_strategy` — 심판·고객봇이 전략 id 를 못 본다
  (결과 조작 여지 차단)
- `tests/test_budget.py::test_hard_limit_refuses_call_before_spending` — 하드 리밋 초과 호출은 안 나간다

---

## 6. 트러블슈팅

| 증상 | 원인/대응 |
|---|---|
| `ModuleNotFoundError: app` | 루트에서 `python -m scripts.<name>` 으로 실행. 편집 설치 `.pth` 가 환경에 따라 안 잡힌다(pytest 는 `pythonpath=["."]` 로 해결돼 있다) |
| `make check` 픽스처 실패 | 출력의 `!` 항목이 정확한 위반 내용이다. 참조 오타·범위 이탈·라벨 불일치 순으로 흔하다 |
| `/health/detail` `status: degraded` | `data.load_errors` 확인 → 픽스처 JSON 문법/필드 오류 |
| 상담이 자산을 인용하지 않는다 | 전략이 S1/S3 면 정상(정책상 미인용). S2 인데 비면 `owned_assets` 가 비었거나 AI2 가 필드를 안 채운 것 |
| `X-Degraded: true` | 업스트림 폴백. 응답 `trace` 에 단계별 사유가 있다. 화면은 정상 동작 |
| Lab 실행이 409 | 의도된 게이트. 대시보드는 비용 다이얼로그, CLI 는 `--yes` 필요 |
| 캐시 히트율 0% | LLM 미연결이면 호출 자체가 없다(정상). 연결 상태에서 0%면 프롬프트에 비결정적 값 의심 |
| Lab 결과가 안 보인다 | `make lab --yes` (규칙 모델이면 약 1초) 후 `/lab` 새로고침 |
| DB 스키마 변경 후 오류 | `make clean-db` (시드는 픽스처라 잃는 게 없다) |

---

## 7. 절대 하지 말 것

- **계약(`contracts/`) 필드를 제거·개명하지 않는다.** 추가는 옵셔널 필드로만. 팀 4개 모듈이 이걸 본다
- **픽스처를 직접 읽는 코드를 새로 만들지 않는다.** provider 경유만
- **판정 함수(`rule_verdict`/`evaluate_turn`/`extract_features`)에 전략 id 를 넘기지 않는다.**
  결과 조작 여지가 생긴다(테스트가 막는다)
- **`owned_assets_used` 플래그를 없애거나 항상 true 로 만들지 않는다.** 제품 실패를 관측하는 장치다
- **캐시를 끄지 않는다**(`LLM_CACHE_ENABLED=false`). 같은 프롬프트에 매번 과금된다
- **프롬프트에 현재 시각·UUID·랜덤값을 넣지 않는다**
- **`LLM_DRY_RUN` 없이 Lab 을 반복 실행하지 않는다.** 먼저 `make estimate`
- **발표 직전에** 픽스처·`REFERENCE_NOW`·`make clean-cache` 를 건드리지 않는다
- 데이터셋 관련 코드를 새로 쓰지 않는다(미확정). 필요하면 `scripts/_deferred/` 복원

---

## 8. 파일 인덱스

| 경로 | 역할 |
|---|---|
| `contracts/` | 팀 인터페이스(6개 엔드포인트). `registry.py` 가 문서·예시 생성의 출처 |
| `fixtures/` | 시드 데이터 12/6/18/3 (지금 유일한 시드 소스) |
| `config/llm_capabilities.json` | 능력 플래그(vision=false 확정) |
| `config/model_routing.yaml` | 용도 → 티어 → 모델. `/models` 조회 후보 목록 |
| `config/model_pricing.yaml` | 모델 단가(예산 계산 근거) |
| `app/data/provider.py` | **데이터 경계.** Fixture/Dataset provider |
| `app/store.py` | provider 위의 인메모리 조회 캐시 |
| `app/llm/client.py` | 게이트웨이(라우팅→캐시→드라이런→예산→호출→기록) |
| `app/llm/budget.py` | 3단 예산 가드 + 사용량 집계 |
| `app/adapters/` | 모듈별 Mock/Http + 레지스트리(전환 지점) |
| `app/services/orchestrator.py` | `/session/advise` 5단계 + 인용 검증 |
| `app/intent_rules.py` | 망설임 분류 규칙(목 응답 = 라벨 도출과 동일 규칙) |
| `app/clienteling_rules.py` | 상담 문구 조립(LLM 폴백 겸 기준선) |
| `app/lab/` | Lab: `persona_bot` / `judge` / `runner` / `cost` / `summary` / `static/lab.html` |
| `app/demo.py` | 데모 시나리오 로딩·검증 |
| `app/routers/` | health / session / modules / catalog / lab / demo / ops |
| `scripts/validate_fixtures.py` | 픽스처 검증(`make check` 에 포함) |
| `scripts/estimate_cost.py` | 드라이런 비용 추정 |
| `scripts/cache_stats.py` | 캐시 히트율·절감액 |
| `scripts/check_demo.py` | 시나리오 기대값 검증 |
| `scripts/healthcheck.py` | in-process 엔드포인트 점검 |
| `scripts/warm_cache.py` | 데모 캐시 워밍업(과금 시 확인 요구) |
| `scripts/_deferred/` | 데이터셋 코드 보관(실행 경로 밖, lint 제외) |
| `data/_deferred/` | 데이터셋 기반 산출물 보관(런타임 미사용) |

---

## 9. 알려진 한계 (인수인계 시점)

1. **Lab 수치는 규칙 모델 결과다.** LLM 미연결 상태에서는 페르소나 봇·심판이 규칙이고, 그 규칙에
   "고객은 자기 물건 근거를 중시한다"는 가정이 있어 S2 우세가 부분적으로 순환이다. 대시보드·CLI 에
   캐비어트를 표시한다. `LLM_API_KEY` 를 넣으면 같은 하네스로 실제 언어 효과를 측정한다.
2. **단가표는 참고치다.** 대회 API 실단가 확정 시 `config/model_pricing.yaml` 을 먼저 고쳐야
   예산 숫자가 맞는다.
3. **상품 이미지가 없다.** `image_path` 는 플레이스홀더이고 프론트가 더미 이미지를 채워야 한다.
4. **개체 지문 등록 CLI 는 보류**(`scripts/_deferred/register_fingerprint.py`). 목 어댑터는 경로
   규약(`data/fingerprints/{asset_id}/{angle}_{index}.jpg`)만으로 판정한다.
5. **AI1 학습·평가셋 없음.** 데이터셋 미확정 때문이며, 이전 산출물이 `data/_deferred/exports/` 에
   스키마 예시로 남아 있다.
6. **드라이런 추정은 보수적**이다(출력 토큰을 `max_tokens` 상한으로 잡는다). 실제는 더 적게 나온다.
