"""환경 설정 단일 출처.

전환 지점(어댑터 모드 / 데이터 소스)만 확실히 분리하는 것이 이 파일의 목적이다.
그 외 값은 기본값으로 두고 필요할 때만 env 로 덮는다.
"""

from __future__ import annotations

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
EXPORTS_DIR = ROOT / "exports"
CACHE_DIR = ROOT / ".cache"
DOCS_DIR = ROOT / "docs"

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
    asset_base_url: str = "http://localhost:8103"
    fingerprint_base_url: str = "http://localhost:8104"
    condition_base_url: str = "http://localhost:8105"

    # ── 데이터 ────────────────────────────────────────────────
    data_source: Literal["external", "synth"] = "external"
    db_path: Path = DATA_DIR / "app.db"
    seed: int = 42

    # ── LLM ───────────────────────────────────────────────────
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_judge_model: str = ""
    llm_temperature: float = 0.0
    llm_seed: int = 42
    llm_timeout_seconds: float = 30.0
    llm_max_tokens: int = 700

    # ── 데모 안정화 ────────────────────────────────────────────
    demo_mode: bool = False
    upstream_timeout_seconds: float = 5.0
    upstream_retries: int = 1

    # ── Persona Bot Lab ───────────────────────────────────────
    lab_concurrency: int = 4
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
    def llm_enabled(self) -> bool:
        """실제 LLM 호출이 가능한지. 키가 없으면 결정적 템플릿 폴백으로 동작한다."""
        return bool(self.llm_api_key and self.llm_base_url)

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
