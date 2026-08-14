# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 정체성

럭셔리 브랜드용 AI 클라이언텔링 서비스(해커톤). 두 축이 결합된다.

1. **개체 지문(fingerprint)** — 제품의 미세 텍스처(가죽 결, 스티치)로 개체 단위 등록/인증
2. **AI 클라이언텔링** — 구매 망설임 원인을 분류하고, 고객이 **실제 소유한 제품 + 컨디션 점수**를 근거로 상담

핵심 차별점은 "고객을 아는 AI"가 아니라 **"고객의 물건을 아는 AI"**다.
→ 이 레포에서 상담 응답이 `cited_asset_ids` 없이 나가면 그것은 **제품 실패**로 취급한다.
`/session/advise`는 그 경우 `owned_assets_used=false`를 응답에 실어 관측 가능하게 만든다. 이 플래그를 없애거나 무조건 true로 만드는 변경은 하지 않는다.

## 이 레포의 담당 범위

6인 팀 중 **통합/데모 담당자**의 코드베이스다. AI 모델 학습은 이 레포에서 하지 않는다.

- 담당: API 계약 정의, 데이터 파이프라인, 오케스트레이터 + 목 어댑터, Persona Bot Lab, 데모 안정화
- 비담당(다른 팀원): 인텐트 분류 모델(AI1), 상담 생성 모델(AI2), 개체 지문 임베딩/컨디션 CV(백엔드)
- 비담당 모듈은 **목(mock)으로 두고 계약만 정확히 맞춘다.** 목을 실제 모델로 대체하는 일은 `ADAPTER_MODE`/모듈별 env 전환으로만 한다.

## 확정된 두 제약 (이 레포의 모든 설계 판단의 전제)

1. **대회 API 에 비전 모델이 없다(텍스트 전용).** `config/llm_capabilities.json` 의
   `vision: false` 를 신뢰하고 런타임 탐지를 하지 않는다. **이미지를 프롬프트에 넣는 코드를
   만들지 않는다** — 호출이 실패하면서 토큰만 태운다. 컨디션 진단의 이미지 채점은 백엔드
   담당이 고전 CV 로 구현하며 계약(`POST /condition/score`)은 불변이다.
2. **크레딧 총액 100달러, 초과 시 복구 불가.** 모든 LLM 호출은 `app/llm/` 게이트웨이를 지나고
   용도 태그(purpose)를 갖는다. 하드 리밋 85달러를 넘길 호출은 **실행 전에** 거부된다.

**외부 데이터셋 미확정.** 시드는 `fixtures/*.json`(손으로 작성)이고 접근은
`app/data/provider.py` 의 `SeedDataProvider` 만 지난다. 데이터셋 관련 코드는 삭제하지 않고
`scripts/_deferred/` 에 보관돼 있다(ruff/mypy 제외 대상). **데이터셋 코드를 새로 쓰지 않는다.**

## 자주 쓰는 명령

```bash
make setup     # uv venv (Python 3.11) + 의존성 설치
make check     # ruff + mypy + 픽스처 검증
make verify    # check + pytest + 헬스체크 + 데모 시나리오
make dev       # 서버 기동 (목 모드, :8000)
make demo      # DEMO_MODE=true 기동 + 캐시 워밍업
make lab       # Persona Bot Lab (예상 비용 확인 후 실행)
make estimate  # 드라이런 비용 추정 — Lab 돌리기 전에 항상
make cache-stats # 캐시 히트율·절감액 (재실행 90% 미만이면 프롬프트에 비결정적 값)
make demo-check # 데모 시나리오 3종 검증 (발표 직전 필수)
make fixtures  # 픽스처 검증만
make clean-db  # SQLite 삭제 (시드는 fixtures/ 에 있어 영향 없음)
```

테스트:

```bash
uv run pytest                                   # 전체
uv run pytest tests/test_orchestrator.py -k cited -q   # 단일 테스트
uv run ruff check . && uv run ruff format --check .
uv run mypy .
```

## 아키텍처 — 읽는 순서

1. `contracts/` — **모든 모듈의 인터페이스 단일 출처(single source of truth).** Pydantic v2 모델.
   팀 전체가 이 파일 + `docs/CONTRACTS.md`만 보고 자기 모듈을 붙인다. 계약 변경은 `docs/CONTRACTS.md`와
   `contracts/examples/*.json`을 **같은 커밋에서** 갱신한다.
2. `app/data/provider.py` — **데이터 접근의 유일한 경계.** `SeedDataProvider` Protocol +
   `FixtureProvider`(사용 중) + `DatasetProvider`(스텁). `SEED_SOURCE=fixture|dataset`.
   런타임 조회는 `app/store.py`(provider 위의 인메모리 캐시)를 경유한다.
   **픽스처 파일을 직접 읽는 코드를 다른 곳에 만들지 않는다.**
3. `app/llm/` — 게이트웨이. `client`(호출) / `budget`(3단 가드) / `routing`(용도→티어→모델) /
   `pricing`(토큰·단가). 모든 호출은 `purpose=` 를 넘긴다. 새 용도는
   `config/model_routing.yaml` 에 티어를 지정한다(태그 없으면 저가 티어로 떨어진다).
4. `app/adapters/` — 모듈별로 `Mock*Adapter` / `Http*Adapter` 두 구현이 동일 Protocol을 만족한다.
   `app/adapters/registry.py`가 env를 읽어 실제 인스턴스를 고른다.
   - `ADAPTER_MODE=mock|http` (전역) + `INTENT_ADAPTER`, `CLIENTELING_ADAPTER`, `ASSET_ADAPTER`,
     `FINGERPRINT_ADAPTER`, `CONDITION_ADAPTER` (모듈별 오버라이드, 전역보다 우선)
   - **목은 provider 를 통해 픽스처 실데이터를 읽어 응답한다.** 하드코딩 더미 문자열 금지.
   - `MockConditionAdapter` 는 **이미지를 보지 않는다**(비전 부재 확정). `image_paths` 가 와도 무시.
5. `app/services/orchestrator.py` — `/session/advise`의 5단계 플로우(인텐트 → 자산 조회 → 컨디션
   우선 정렬 → 상담 호출 → **인용 검증**). 데모의 심장.
6. `app/lab/` — Persona Bot Lab. 페르소나 봇(고객) ↔ 오케스트레이터(직원) ↔ 심판.
   5 페르소나 × 3 전략 × N회. 결과·대화 전문은 SQLite에 저장하고 `/lab` 대시보드에서 조회.
   - **판정 함수는 전략 id를 보지 않는다**(`rule_verdict`, `evaluate_turn`, `extract_features`).
     테스트가 시그니처와 소스를 검사해 이를 고정한다. 전략이 만든 *문구 차이*만이 결과를 갈라야 한다.
   - LLM 미연결이면 페르소나·심판이 규칙 모델이다. 그 경우 S2 우세는 규칙의 가정이 반영된
     순환이므로 캐비어트를 지운 채 수치를 인용하지 않는다.
7. `app/demo.py` + `data/demo_scenarios.yaml` — 데모 시나리오 3종. 고객·상품·전략·세션을 id로
   못박고 `expect` 블록을 `make demo-check`가 검증한다.
8. `app/personas.py` / `app/strategies.py` — `data/personas.yaml`, `data/strategies.yaml` 로딩.
   페르소나는 Phase 2에서 만든 **실제 고객**에 바인딩된다(`validate_bindings()`가 검사).
9. `scripts/` — 픽스처 검증 + 문서 생성기 + Lab/데모/비용 CLI.
   데이터셋 코드는 `scripts/_deferred/`(실행 경로 밖).

## 시드 픽스처 불변식 (깨면 데모가 깨진다)

- **기준시각은 `app/config.py`의 `REFERENCE_NOW`(2026-08-14T12:00+09:00) 하나뿐이다.**
- **픽스처 타임스탬프는 고정값이다.** 현재 시각·UUID가 프롬프트에 들어가면 LLM 캐시가 매 실행
  무효화되고 예산이 샌다. `make cache-stats` 로 재실행 히트율(≥90%)을 확인한다.
- 데모 전제 3종은 반드시 존재한다: **AS-0001 컨디션 71점 핸들 마모 임계 근접**, AS-0016 97점,
  AS-0007 54점. `make fixtures` 가 검사한다.
- 시나리오 라벨은 픽스처에 적지 않고 **이벤트 시퀀스에 `app/intent_rules.py` 규칙을 적용해 도출**한다.
  `label_hint` 와 어긋나면 검증이 실패한다.
- 픽스처를 고치면 `make fixtures` → `make demo-check` 를 반드시 통과시킨다.

## 예산 규율 (하드 룰)

- 새 LLM 호출을 추가하면 **반드시 `purpose=` 를 넘긴다.** 태그 없는 호출은 저가 티어로 떨어지고
  용도별 비용 분해가 깨진다.
- 캐시를 끄지 않는다(`LLM_CACHE_ENABLED=false` 금지). 프롬프트에 비결정적 값을 넣지 않는다.
- Lab 을 돌리기 전에 `make estimate`. 실행 API/CLI 의 확인 게이트를 우회하지 않는다.
- 하드 리밋(85달러)을 100으로 올리지 않는다. 15달러는 발표 당일 재실행 여유분이다.

## 실측 보고 원칙 (Persona Bot Lab)

시뮬레이션 결과를 조작하거나 특정 전략(S2)이 이기도록 하드코딩하지 않는다. 실측값을 그대로 저장한다.
S2가 지면 그 원인을 분석할 수 있어야 하는 것이 이 Lab의 존재 이유다.

## LLM 호출

OpenAI 호환 엔드포인트로만 호출한다(`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`). 로컬 vLLM과 상용 API
양쪽에 붙어야 하므로 특정 벤더 SDK를 직접 import하지 않는다. 진입점은 `app/llm.py` 하나로 유지한다.

- `temperature=0` + 시드 고정이 기본. 데모 재현성이 우선이다.
- `DEMO_MODE=true`면 모든 LLM 응답을 `.cache/llm/`에 디스크 캐시하고 동일 입력은 캐시에서 반환한다.
  네트워크가 끊겨도 데모가 돌아야 한다.
- API 키가 없으면 `app/llm.py`가 **결정적 템플릿 폴백**으로 동작한다(크래시 금지).

## 데모 안정화 규칙

- 모든 업스트림 호출: 타임아웃 5초 + 재시도 1회. 실패 시 사전 준비 응답으로 대체하고 응답 헤더에
  `X-Degraded: true`를 실는다. **화면에 에러를 노출하지 않는다.** 발표 중 빨간 에러 화면이 최악이다.
- `/health/detail`에 어댑터 모드, 최근 응답 상태, 데이터 소스, 캐시 건수를 노출한다(발표 직전 5초 점검용).
- 데모 당일 절차와 사고 대응은 `docs/DEMO_RUNBOOK.md`. 발표 직전 `build_catalog --force`와
  `REFERENCE_NOW` 변경은 금지(대본이 깨진다).
- 팀 백엔드는 이미 다른 필드 스키마로 구현돼 있고 HTTP 어댑터가 레거시 매퍼로 흡수한다.
  차이와 백엔드가 채워야 할 `cited_asset_ids`는 `docs/BACKEND_INTEGRATION.md`.

## 코드 스타일

- 타입 힌트 빠짐없이. ruff + mypy 통과가 머지 조건.
- 해커톤 코드다. 과도한 추상화는 하지 않는다. **단 어댑터 전환 지점과 데이터 소스 전환 지점만은 확실히 분리한다.**
- Lab 대시보드는 FastAPI가 서빙하는 단일 HTML + vanilla JS. 프론트 담당(별도 레포)과 충돌을 피하려는 의도적 선택이므로 빌드 툴체인을 도입하지 않는다.
