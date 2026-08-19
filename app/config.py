"""환경 설정 단일 출처.

전환 지점(어댑터 모드 / 데이터 소스)만 확실히 분리하는 것이 이 파일의 목적이다.
그 외 값은 기본값으로 두고 필요할 때만 env 로 덮는다.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
IMAGES_DIR = PROCESSED_DIR / "images"
FINGERPRINT_DIR = DATA_DIR / "fingerprints"
FIXTURES_DIR = ROOT / "fixtures"
CONFIG_DIR = ROOT / "config"
CACHE_DIR = ROOT / ".cache"
DOCS_DIR = ROOT / "docs"

KST = timezone(timedelta(hours=9))

_DEFAULT_REFERENCE_NOW = datetime(2026, 8, 14, 12, 0, 0, tzinfo=KST)


def reference_now() -> datetime:
    """모든 시간 계산의 기준시각(고정). env `REFERENCE_NOW` 로만 덮을 수 있다.

    컨디션 점수가 경과 연수의 함수라서 `datetime.now()` 를 쓰면 매일 점수가 흔들리고
    "컨디션 71점" 이라는 데모 대사가 깨진다. 빌더와 런타임이 같은 기준시각을 써야 한다.
    """
    raw = os.environ.get("REFERENCE_NOW")
    if not raw:
        return _DEFAULT_REFERENCE_NOW
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return _DEFAULT_REFERENCE_NOW
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)


REFERENCE_NOW = reference_now()

AdapterMode = Literal["mock", "http"]
ModuleKey = Literal["intent", "clienteling", "asset", "fingerprint", "condition"]
MODULE_KEYS: tuple[ModuleKey, ...] = ("intent", "clienteling", "asset", "fingerprint", "condition")


class Settings(BaseSettings):
    """전 서비스 공통 설정. `.env` 를 읽는다."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # ── 어댑터 전환 ────────────────────────────────────────────
    adapter_mode: AdapterMode = "mock"
    intent_adapter: AdapterMode | None = None
    clienteling_adapter: AdapterMode | None = None
    asset_adapter: AdapterMode | None = None
    fingerprint_adapter: AdapterMode | None = None
    condition_adapter: AdapterMode | None = None

    intent_base_url: str = "http://localhost:8101"
    clienteling_base_url: str = "http://localhost:8102"
    # asset/fingerprint/condition 은 백엔드 한 프로세스가 :8001 에서 셋 다 서빙한다.
    asset_base_url: str = "http://localhost:8001"
    fingerprint_base_url: str = "http://localhost:8001"
    condition_base_url: str = "http://localhost:8001"

    # ── 시드 데이터 ────────────────────────────────────────────
    # 외부 데이터셋 미확정 → 손으로 쓴 픽스처가 기본. 데이터셋 확정 시 dataset 으로 전환한다.
    seed_source: Literal["fixture", "dataset"] = "fixture"
    db_path: Path = DATA_DIR / "app.db"
    seed: int = 42

    # ── LLM ───────────────────────────────────────────────────
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    #: 상위 티어(상담·심판). config/model_routing.yaml 의 tier→model 매핑에서 덮어쓸 수 있다.
    llm_model: str = "gpt-4o-mini"
    #: 저가 티어(페르소나·분류·컨디션 소견). 비어 있으면 llm_model 을 쓴다.
    llm_model_cheap: str = ""
    llm_judge_model: str = ""
    llm_temperature: float = 0.0
    llm_seed: int = 42
    llm_timeout_seconds: float = 30.0
    llm_max_tokens: int = 700
    llm_max_concurrency: int = 4
    #: 캐시는 기본 활성화다. 끄려면 명시적으로 false 로 둬야 한다(예산 사고 방지).
    llm_cache_enabled: bool = True
    #: true 면 실제 호출 없이 토큰/비용만 추정한다(make estimate).
    llm_dry_run: bool = False
    llm_models_discovery: bool = True

    # ── 예산 (총액 100달러, 초과 시 복구 수단 없음) ──────────────
    llm_budget_total_usd: float = 100.0
    llm_budget_warn_usd: float = 60.0
    llm_budget_hard_usd: float = 85.0
    #: 세션 원가를 원화로 환산할 때 쓰는 고정 환율(실시간 조회하지 않는다).
    usd_krw: float = 1380.0

    # ── 데모 안정화 ────────────────────────────────────────────
    demo_mode: bool = False
    upstream_timeout_seconds: float = 5.0
    upstream_retries: int = 1

    # ── Persona Bot Lab ───────────────────────────────────────
    lab_concurrency: int = 4  # 하위 호환. 실제 동시성은 lab_max_concurrency 를 본다
    lab_runs_per_pair: int = 3
    lab_max_turns: int = 6

    def module_mode(self, module: ModuleKey) -> AdapterMode:
        """모듈별 어댑터 모드. 개별 오버라이드가 전역보다 우선한다."""
        override: AdapterMode | None = getattr(self, f"{module}_adapter")
        return override or self.adapter_mode

    def module_base_url(self, module: ModuleKey) -> str:
        url: str = getattr(self, f"{module}_base_url")
        return url.rstrip("/")

    @property
    def judge_model(self) -> str:
        return self.llm_judge_model or self.llm_model

    @property
    def cheap_model(self) -> str:
        return self.llm_model_cheap or self.llm_model

    @property
    def lab_max_concurrency(self) -> int:
        """LLM_MAX_CONCURRENCY 가 우선. 없으면 기존 LAB_CONCURRENCY 를 쓴다."""
        return self.llm_max_concurrency or self.lab_concurrency

    @property
    def llm_enabled(self) -> bool:
        """실제 LLM 호출이 가능한지. 키가 없으면 결정적 템플릿 폴백으로 동작한다."""
        return bool(self.llm_api_key and self.llm_base_url)

    @property
    def llm_active(self) -> bool:
        """LLM 코드 경로를 태울지 여부.

        드라이런은 **키가 없어도** 이 경로를 타야 한다. 그래야 `make estimate` 가 실제와 같은
        호출 횟수·프롬프트 크기로 비용을 추정할 수 있다(호출은 하지 않고 기록만 남는다).
        """
        return self.llm_enabled or self.llm_dry_run

    @property
    def llm_cache_dir(self) -> Path:
        return CACHE_DIR / "llm"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """프로세스 전역 설정 싱글턴."""
    return Settings()


def reload_settings() -> Settings:
    """테스트/스크립트에서 env 를 바꾼 뒤 다시 읽기 위한 우회로."""
    get_settings.cache_clear()
    return get_settings()
