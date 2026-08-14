# Luxe Clienteling — 통합/데모 레이어

럭셔리 브랜드용 AI 클라이언텔링 서비스의 **통합/데모 담당** 코드베이스.
"고객을 아는 AI"가 아니라 **"고객의 물건을 아는 AI"**라는 것이 이 제품의 차별점이고,
그 차별점이 실제로 작동하는지를 이 레이어가 측정한다(상담이 소유 자산을 인용하지 않으면
`owned_assets_used=false` 로 드러난다).

## 지금의 두 가지 제약 (확정)

| 제약 | 대응 |
|---|---|
| **대회 API 에 비전(이미지 입력) 모델이 없다. 텍스트 전용.** | `config/llm_capabilities.json` 에 `vision: false` 를 못박고 런타임 탐지를 하지 않는다. 이미지를 프롬프트에 넣는 경로는 존재하지 않으며 테스트로 고정했다. 컨디션 진단은 목이 이미지를 보지 않고 픽스처 값을 반환하며, 이미지 기반 실시간 채점은 **백엔드 담당이 고전 CV 로 구현**한다(계약 불변). |
| **크레딧 총액 100달러, 초과 시 복구 수단 없음.** | 3단 예산 가드(총 100 / 경고 60 / **하드 85**), 호출 전 비용 추정 후 거부, 용도별 모델 티어 분리, 캐시 기본 ON, 드라이런(`make estimate`), `/ops` 대시보드. |

**외부 데이터셋은 미확정**이다. 시드 데이터는 손으로 쓴 `fixtures/*.json` 이고, 접근은
`app/data/provider.py` 의 `SeedDataProvider` 한 곳만 지난다. 데이터셋이 정해지면
`DatasetProvider` 를 채우고 `SEED_SOURCE=dataset` 으로 바꾸면 된다.
데이터셋 관련 코드는 지우지 않고 `scripts/_deferred/` 에 보관돼 있다.

관련 문서: [`docs/CONTRACTS.md`](docs/CONTRACTS.md) (팀 인터페이스) ·
[`docs/BACKEND_INTEGRATION.md`](docs/BACKEND_INTEGRATION.md) ·
[`docs/DEMO_RUNBOOK.md`](docs/DEMO_RUNBOOK.md) ·
[`scripts/_deferred/README.md`](scripts/_deferred/README.md) (보류 코드 복원 절차)

## 1. 실행 방법

```bash
make setup      # uv venv(3.11) + 의존성 + .env 생성
make check      # ruff + mypy + 픽스처 검증  ← 여기서 통과해야 나머지가 의미 있다
make dev        # 목 모드 서버 :8000
```

확인:

```bash
curl -s localhost:8000/health/detail | jq   # 시드 소스·어댑터·능력 플래그·예산 한눈에
open http://localhost:8000/lab             # Persona Bot Lab (실행 전 비용 확인 필수)
open http://localhost:8000/ops             # 예산 게이지·세션 원가
open http://localhost:8000/docs            # OpenAPI
```

데모 당일:

```bash
make estimate   # 드라이런 비용 추정 (실제 호출 없음) — Lab 돌리기 전에 항상
make demo       # 캐시 워밍업 + 데모 모드 기동
make demo-check # 시나리오 3종 기대값 검증 (문구 전문 출력)
```

| 명령 | 설명 |
|---|---|
| `make setup` | venv + 의존성 + `.env` |
| `make check` | ruff + mypy + 픽스처 검증 |
| `make verify` | check + pytest + 헬스체크 + 시나리오 검증 (커밋 전) |
| `make dev` / `make demo` | 개발 서버 / 데모 모드 서버 |
| `make lab` | Persona Bot Lab (예상 비용 확인 후 실행, `--yes` 로 생략) |
| `make estimate` | 드라이런 비용 추정 |
| `make cache-stats` | 캐시 히트율·절감액 |
| `make fixtures` | 픽스처만 검증 |
| `make clean-db` / `make clean-cache` | SQLite / LLM 캐시 삭제 |

스크립트는 루트에서 `python -m scripts.<name>` 으로 실행한다.

## 2. 시드 데이터 (픽스처)

```
fixtures/products.json        상품 12개  (BAG 4 / SHOES 3 / WATCH 2 / WALLET 2 / BELT 1)
fixtures/customers.json       고객 6명   (VIP 2 / ESTABLISHED 3 / NEW 1, 5명은 페르소나 바인딩)
fixtures/assets.json          개체 18개  (컨디션 54~97)
fixtures/session_events.json  시나리오 3종 (사이즈 / 가격 / 재고, 9~11 이벤트)
```

데모가 성립하려면 아래 세 개가 반드시 있어야 하고, `make fixtures` 가 검사한다.

- **AS-0001 컨디션 71점 + 핸들 마모 임계 근접** — 발표 대본의 핵심 대사
- **AS-0016 컨디션 97점** — 대비용 신품급
- **AS-0007 컨디션 54점** — 리세일/케어 시나리오용

그 밖에 검사하는 것: 계약 스키마, 참조 정합성, 가격 대역(150만~1,200만), 재고 음수 금지,
**시나리오 이벤트에서 규칙이 도출한 라벨이 `label_hint` 와 일치하는지**, 페르소나 바인딩,
이벤트 타임스탬프가 고정값인지(현재 시각이 섞이면 LLM 캐시가 매 실행 무효화된다).

`image_path` 는 플레이스홀더다. 프론트 담당이 더미 이미지를 채우고 실물은 데이터셋 확정 후 붙인다.

## 3. 예산 통제 (100달러)

```bash
make estimate                    # 드라이런: 시나리오 3종 + Lab 1회 비용 추정
make cache-stats --by-run        # 히트율. 재실행 90% 미만이면 프롬프트에 비결정적 값이 있다
curl -s localhost:8000/ops/summary | jq '.budget, .per_session'
```

- **호출 전 게이트**: 입력 토큰을 추정해 하드 리밋(85달러)을 넘길 호출은 **실행하지 않는다**.
  사후 집계로는 늦다. 거부되면 캐시 또는 결정적 템플릿으로 응답한다.
- **용도별 티어** (`config/model_routing.yaml`): 상담·심판 = 상위 / 페르소나·분류·컨디션 소견 = 저가.
- **캐시 기본 ON**: 키에 프롬프트·모델·temperature·seed 를 넣어 모델을 바꾸면 자동 무효화된다.
- **Lab 실행 전 확인**: `/lab/run` 은 `confirm=true` 없이 409(예상 비용 동봉). 대시보드는
  비용 다이얼로그를 띄우고, CLI 는 `--yes` 를 요구한다.

드라이런 실측 (high=`gpt-4o` / low=`gpt-4o-mini` 가정, 캐시 미스 상한):

| 항목 | 호출 | 비용 |
|---|---|---|
| Lab 1회 (45세션) | 292건 (상담 146 / 페르소나 101 / 심판 45) | **$1.13 ≈ 1,563원** |
| 상담 세션 1건 | ~6.5건 | **$0.0252 ≈ 35원** |
| 데모 시나리오 3종 재생 | 3건 | $0.0165 ≈ 23원 |
| 전부 상위 티어로 돌렸다면 | 292건 | $1.47 (티어 분리로 **23% 절감**) |

단가는 `config/model_pricing.yaml` 이고 **대회 API 실단가가 확정되면 이 파일을 먼저 고친다**.
미등록 모델은 보수적 기본값(입력 $1/1M, 출력 $3/1M)으로 계산한다.

## 4. 팀원별 전달 사항

- **전원**: 대회 API 는 **텍스트 전용**이다. 이미지 입력을 전제한 설계를 하지 말고, 필요하면
  로컬 모델이나 고전 CV 로 간다. `config/llm_capabilities.json` 이 단일 출처다.
- **전원**: LLM 호출은 **용도 태그와 함께 게이트웨이를 지나야** 예산이 통제된다.
  `get_llm().complete(messages, purpose="clienteling", ...)` 형태로 쓰고 새 용도는
  `config/model_routing.yaml` 에 티어를 지정한다. 태그 없이 호출하면 저가 티어(`other`)로 떨어진다.
- **AI1 (인텐트)**: `POST /intent/classify` 구현. 지금 목은 `app/intent_rules.py` 규칙 엔진이라
  "규칙 대비 개선"을 같은 기준으로 비교할 수 있다. 학습·평가 데이터는 데이터셋 확정 후 제공한다
  (기존 산출물은 `data/_deferred/exports/` 에 참고용으로 남겨 뒀다).
- **AI2 (상담)**: `POST /clienteling/reply` 구현. **`owned_assets` 가 있으면 `cited_asset_ids` 를
  반드시 채운다** — 비면 오케스트레이터가 `owned_assets_used=false` 로 표시하고 Lab 의 S2 효과가
  0으로 측정된다. 프롬프트 예시는 `app/adapters/clienteling.py` 의 `build_prompt`.
- **백엔드**: `POST /condition/score` 를 고전 CV 로 구현한다. **계약은 그대로 유지**되므로 목을
  `CONDITION_ADAPTER=http` 로 바꾸는 것만으로 교체된다. 기존 API 와의 필드 차이는
  `docs/BACKEND_INTEGRATION.md` 에 매핑표가 있다(자동 흡수되지만 `cited_asset_ids` 는 예외).
- **프론트**: `POST /session/advise` 하나만 렌더하면 된다. 부가 조회는 `/catalog`, `/customers`,
  `/sessions`. 응답 헤더 `X-Degraded`, `X-Owned-Assets-Used` 로 폴백·차별점 작동을 알 수 있다.
  상품 이미지는 플레이스홀더 경로이므로 더미 이미지를 채워 달라.

## 5. 목 → 실제 전환

```bash
INTENT_ADAPTER=http INTENT_BASE_URL=http://localhost:8101 make dev   # 모듈별 부분 전환
CONDITION_ADAPTER=http make dev                                      # 백엔드 CV 채점 붙일 때
ADAPTER_MODE=http make dev                                           # 전역(마지막에)
```

업스트림이 죽어도 `/session/advise` 는 200 + `X-Degraded: true` 로 응답하고 규칙·템플릿 폴백
문구를 유지한다. 어느 단계가 폴백됐는지는 응답 `trace` 에 있다.

## 6. 데이터셋 확정 시 교체 지점

1. `app/data/provider.py` 의 `DatasetProvider` 구현 (5개 메서드) → `SEED_SOURCE=dataset`
2. `scripts/_deferred/` 의 빌더 복원 (`README.md` 의 절차, ruff/mypy 제외 목록에서 제거)
3. `data/personas.yaml` / `data/demo_scenarios.yaml` 의 고객·상품·세션 id 갱신
4. `fixtures/` 는 회귀 테스트용으로 유지(테스트가 픽스처 규모를 검증한다)
5. `python -m scripts.validate_fixtures --provider dataset` 로 같은 검증 통과 확인

**오케스트레이터·어댑터·Lab·데모 코드는 손대지 않는다.** 그게 provider 를 둔 이유다.

## 7. 구조

```
contracts/       팀 전체 인터페이스(Pydantic v2). docs/CONTRACTS.md 는 여기서 생성
fixtures/        손으로 쓴 시드 데이터 (지금 유일한 시드 소스)
config/          llm_capabilities.json / model_routing.yaml / model_pricing.yaml
app/
  data/          SeedDataProvider — 데이터셋 교체의 유일한 경계
  llm/           게이트웨이(client) + 예산(budget) + 라우팅(routing) + 단가(pricing)
  adapters/      모듈별 Mock/Http 어댑터 + 레지스트리(전환 지점)
  services/      오케스트레이터(5단계 + 인용 검증)
  lab/           Persona Bot Lab (고객 봇 / 심판 / 러너 / 비용추정 / 대시보드)
  intent_rules.py       망설임 분류 규칙(목 응답과 라벨 도출이 공유)
  clienteling_rules.py  상담 문구 조립(LLM 폴백 겸 기준선)
scripts/         검증·Lab·데모·비용 CLI  (_deferred/ = 데이터셋 코드 보관)
data/_deferred/  데이터셋 기반 산출물 보관(런타임 미사용)
```

## 8. 재현성 규칙

- 기준시각은 `app/config.py` 의 `REFERENCE_NOW`(2026-08-14T12:00+09:00) 고정.
- 시나리오는 고객·상품·세션 id 를 못박고 `make demo-check` 로 기대값을 검증한다.
- 픽스처 타임스탬프는 고정값이다. 현재 시각이 프롬프트에 들어가면 캐시가 죽고 예산이 샌다.
- Lab 반복 회차는 초기 신뢰도 ±0.3 과 오프닝 변형만 다르다(결정적 시스템에서 같은 조건 N회는
  의미가 없어서 그렇게 설계했다).
