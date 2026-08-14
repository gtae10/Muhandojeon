PY := .venv/bin/python
UVICORN := .venv/bin/uvicorn
PORT ?= 8000

.DEFAULT_GOAL := help
.PHONY: help setup contracts fixtures check verify test fmt dev demo lab estimate cache-stats \
        demo-check healthcheck clean-db clean-cache

help:  ## 사용 가능한 타깃 목록
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}'

setup:  ## uv venv(3.11) + 의존성 설치 + .env 생성
	uv venv --python 3.11
	uv pip install -e ".[dev]"
	@test -f .env || cp .env.example .env
	@echo "→ .env 확인: LLM_API_KEY 없으면 결정적 템플릿 폴백으로 동작한다"

fixtures:  ## 시드 픽스처 검증 (계약 스키마 + 참조 정합성 + 데모 전제)
	$(PY) -m scripts.validate_fixtures

contracts:  ## 계약 문서/예시 재생성 (docs/CONTRACTS.md, contracts/examples/*.json)
	$(PY) -m scripts.gen_contracts_doc

check:  ## ruff + mypy + 픽스처 검증
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	.venv/bin/mypy .
	$(PY) -m scripts.validate_fixtures

verify:  ## check + 테스트 + 헬스체크 + 데모 시나리오 (커밋 전 전체 확인)
	$(MAKE) check
	.venv/bin/pytest -q
	$(PY) -m scripts.healthcheck
	$(PY) -m scripts.check_demo

test:  ## pytest
	.venv/bin/pytest -q

fmt:  ## 포맷 + 자동 수정
	.venv/bin/ruff format .
	.venv/bin/ruff check --fix .

dev:  ## 서버 기동 (목 모드, :$(PORT))
	ADAPTER_MODE=mock $(UVICORN) app.main:app --reload --port $(PORT)

demo:  ## 데모 모드 기동 (LLM 디스크 캐시 + 캐시 워밍업)
	DEMO_MODE=true $(PY) -m scripts.warm_cache
	DEMO_MODE=true ADAPTER_MODE=mock $(UVICORN) app.main:app --port $(PORT)

lab:  ## Persona Bot Lab 실행 (5 페르소나 x 3 전략 x N회)
	$(PY) -m scripts.run_lab

estimate:  ## 드라이런 비용 추정 (실제 호출 없음) — Lab 실행 전 필수
	LLM_DRY_RUN=true $(PY) -m scripts.estimate_cost

cache-stats:  ## LLM 캐시 히트율과 절감액
	$(PY) -m scripts.cache_stats

demo-check:  ## 데모 시나리오 3종 검증 (발표 직전, 문구 전문 출력)
	$(PY) -m scripts.check_demo --verbose

healthcheck:  ## in-process 헬스 체크
	$(PY) -m scripts.healthcheck

clean-db:  ## SQLite 삭제 (Lab 결과·LLM 사용량 이력만 사라진다. 시드는 fixtures/ 에 있다)
	rm -f data/app.db
	@echo "삭제: data/app.db (시드 데이터는 fixtures/*.json 이므로 영향 없음)"

clean-cache:  ## LLM 디스크 캐시 삭제 (예산을 다시 쓰게 되므로 주의)
	rm -rf .cache/llm
