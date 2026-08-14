PY := .venv/bin/python
UVICORN := .venv/bin/uvicorn
PORT ?= 8000

.DEFAULT_GOAL := help
.PHONY: help setup contracts docs data data-synth seed dev demo lab check test fmt clean-db clean-cache

help:  ## 사용 가능한 타깃 목록
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## uv venv(3.11) + 의존성 설치
	uv venv --python 3.11
	uv pip install -e ".[dev]"
	@test -f .env || cp .env.example .env
	@echo "→ .env 를 확인하세요 (LLM_API_KEY 없으면 결정적 템플릿 폴백으로 동작)"

contracts:  ## 계약 문서/예시 재생성 (docs/CONTRACTS.md, contracts/examples/*.json)
	$(PY) -m scripts.gen_contracts_doc

docs:  ## 생성 문서 전체 재생성 (계약 + 데이터 출처)
	$(PY) -m scripts.gen_contracts_doc
	$(PY) -m scripts.gen_provenance_doc

data:  ## 데이터 획득 → 정규화 → export (외부 데이터 없으면 자동 synth 폴백)
	-$(PY) -m scripts.fetch_data
	$(PY) -m scripts.build_catalog
	$(PY) -m scripts.build_customers
	$(PY) -m scripts.build_sessions
	$(PY) -m scripts.export_for_team
	$(PY) -m scripts.gen_provenance_doc
	$(PY) -m scripts.seed_db

data-synth:  ## 외부 데이터 무시하고 합성만으로 파이프라인 완주
	DATA_SOURCE=synth $(MAKE) data

seed:  ## data/processed/*.json → SQLite 적재
	$(PY) -m scripts.seed_db

dev:  ## 시드 + 서버 기동 (목 모드, :$(PORT))
	$(PY) -m scripts.seed_db
	ADAPTER_MODE=mock $(UVICORN) app.main:app --reload --port $(PORT)

demo:  ## 데모 모드 기동 (LLM 디스크 캐시 + 캐시 워밍업)
	$(PY) -m scripts.seed_db
	DEMO_MODE=true $(PY) -m scripts.warm_cache
	DEMO_MODE=true ADAPTER_MODE=mock $(UVICORN) app.main:app --port $(PORT)

lab:  ## Persona Bot Lab 시뮬레이션 실행 (5 페르소나 x 3 전략 x N회)
	$(PY) -m scripts.run_lab

check:  ## ruff + mypy + 헬스 체크
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	.venv/bin/mypy .
	$(PY) -m scripts.healthcheck

test:  ## pytest
	.venv/bin/pytest -q

fmt:  ## 포맷 + 자동 수정
	.venv/bin/ruff format .
	.venv/bin/ruff check --fix .

clean-db:  ## SQLite 만 삭제 (data/processed/*.json 은 보존)
	rm -f data/app.db
	@echo "삭제: data/app.db (catalog_luxury.json 등 정규화 산출물은 보존)"

clean-cache:  ## LLM 디스크 캐시 삭제
	rm -rf .cache/llm
