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

## 자주 쓰는 명령

```bash
make setup     # uv venv (Python 3.11) + 의존성 설치
make data      # 데이터 획득 → 정규화 → export (외부 데이터 없으면 synth 폴백)
make dev       # 시드 + 서버 기동 (목 모드, :8000)
make demo      # DEMO_MODE=true 기동 + LLM 캐시 워밍업
make check     # ruff + mypy + 헬스체크
make lab       # Persona Bot Lab 45세션 시뮬레이션 실행(CLI)
make clean-db  # SQLite 삭제 (data/processed/*.json 은 보존)
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
2. `app/adapters/` — 모듈별로 `Mock*Adapter` / `Http*Adapter` 두 구현이 동일 Protocol을 만족한다.
   `app/adapters/registry.py`가 env를 읽어 실제 인스턴스를 고른다.
   - `ADAPTER_MODE=mock|http` (전역) + `INTENT_ADAPTER`, `CLIENTELING_ADAPTER`, `ASSET_ADAPTER`,
     `FINGERPRINT_ADAPTER`, `CONDITION_ADAPTER` (모듈별 오버라이드, 전역보다 우선)
   - **목은 Phase 2 산출 실데이터(`data/processed/*.json`)를 읽어서 응답한다.** 하드코딩 더미 문자열 금지.
3. `app/services/orchestrator.py` — `/session/advise`의 5단계 플로우(인텐트 → 자산 조회 → 컨디션
   우선 정렬 → 상담 호출 → **인용 검증**). 데모의 심장.
4. `app/lab/` — Persona Bot Lab. 페르소나 봇(고객) ↔ 상담 어댑터(직원) ↔ 심판 LLM.
   5 페르소나 × 3 전략 × N회. 결과는 SQLite에 저장하고 `/lab` 대시보드에서 조회.
5. `scripts/` — 데이터 파이프라인. `data/raw/`(원본, gitignore) → `data/processed/`(정규화) → SQLite.

## 데이터 파이프라인 불변식 (깨면 데모가 깨진다)

- **모든 샘플링/분할은 seed=42 고정.** 데모가 매번 달라지면 안 된다. `random`/`polars` 시드를 반드시 명시한다.
- **`data/processed/catalog_luxury.json`은 한 번 만들면 재생성하지 않는다.** 상품명이 바뀌면 발표 대본이 깨진다.
  `scripts/build_catalog.py`는 `--force` 없이 기존 파일을 덮어쓰지 않는다.
- **`transactions_train.csv`(3,000만 행 이상)를 메모리에 올리지 않는다.** polars `scan_csv` lazy만 사용.
- 컨디션 점수·findings·티어는 모두 **결정적 계산**(경과 연수 × 카테고리 마모 계수)이다. 난수로 만들지 않는다.
- 데모 대본 핵심 대사를 위해 **최소 1명은 "컨디션 71점, 핸들 마모 임계 근접" 자산**을 갖는다
  (`scripts/build_customers.py`의 보정 단계). 이 보정을 제거하지 않는다.
- `DATA_SOURCE=external|synth`. 외부 데이터가 없으면 자동으로 synth 폴백하며, **동일 스키마**를 지킨다.
- 어떤 필드가 원본이고 어떤 필드가 합성인지 `docs/DATA_PROVENANCE.md`에 유지한다. 심사위원 Q&A 방어용이다.

## 라이선스 주의

- **MVTec AD는 CC BY-NC-SA 4.0 — 상업적 사용 금지.** 자동 다운로드하지 않는다.
  `data/raw/mvtec/`에 수동으로 놓였을 때만 사용하고, 없으면 조용히 건너뛴다.
- 데이터셋 출처·라이선스·사용 범위는 `docs/DATA_LICENSES.md`에 표로 유지한다.

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

## 코드 스타일

- 타입 힌트 빠짐없이. ruff + mypy 통과가 머지 조건.
- 해커톤 코드다. 과도한 추상화는 하지 않는다. **단 어댑터 전환 지점과 데이터 소스 전환 지점만은 확실히 분리한다.**
- Lab 대시보드는 FastAPI가 서빙하는 단일 HTML + vanilla JS. 프론트 담당(별도 레포)과 충돌을 피하려는 의도적 선택이므로 빌드 툴체인을 도입하지 않는다.
