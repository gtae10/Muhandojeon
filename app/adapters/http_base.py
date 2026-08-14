"""HTTP 어댑터 공통 — 타임아웃 + 재시도 1회 + 상태 기록 + 관용적 응답 파싱.

팀 백엔드가 이미 **다른 필드 이름**으로 구현되어 있는 부분이 있다(예: `price_usd`,
`condition_grade` + `wear_detail`, `/api/users/{id}/assets`, `/api/chat` 의 `reply`).
그래서 응답 파싱을 두 단계로 한다.

1. 우리 계약 모델로 바로 검증 (`docs/CONTRACTS.md` 를 따르는 구현)
2. 실패하면 **레거시 매퍼**로 필드를 옮겨 다시 검증 (이미 만들어진 백엔드)

두 번째 경로를 타면 `last_status` 에 `ok(legacy-mapped)` 로 남아 헬스 대시보드에서 보인다.
필드 차이 목록과 백엔드가 채워야 할 항목은 `docs/BACKEND_INTEGRATION.md` 에 있다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.adapters.base import AdapterBase, UpstreamError
from app.config import Settings, get_settings

logger = logging.getLogger("app.adapters.http")

ModelT = TypeVar("ModelT", bound=BaseModel)


class HttpAdapterBase(AdapterBase):
    """업스트림 호출 공통 로직."""

    def __init__(self, module: str, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        base_url = self.settings.module_base_url(module)  # type: ignore[arg-type]
        super().__init__(module=module, mode="http", target=base_url)
        self.base_url = base_url

    # ── 요청 ──────────────────────────────────────────────────
    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        attempts = 1 + self.settings.upstream_retries
        started = time.perf_counter()
        last_error = ""
        for attempt in range(attempts):
            try:
                response = httpx.request(
                    method,
                    url,
                    json=payload,
                    timeout=self.settings.upstream_timeout_seconds,
                )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(
                    "업스트림 실패 %s %s (%d/%d): %s",
                    method,
                    url,
                    attempt + 1,
                    attempts,
                    last_error,
                )
        elapsed = (time.perf_counter() - started) * 1000
        self.status.record_failure(elapsed, last_error)
        raise UpstreamError(f"{method} {url} 실패: {last_error}")

    def _parse(
        self,
        raw: Any,
        model: type[ModelT],
        legacy_mapper: Callable[[Any], dict[str, Any]] | None,
        started: float,
    ) -> ModelT:
        """계약 모델 → (실패 시) 레거시 매퍼 순으로 파싱한다."""
        elapsed = (time.perf_counter() - started) * 1000
        try:
            parsed = model.model_validate(raw)
            self.status.record_success(elapsed)
            return parsed
        except ValidationError as exc:
            if legacy_mapper is None:
                self.status.record_failure(elapsed, f"계약 불일치: {exc.errors()[:2]}")
                raise UpstreamError(f"{model.__name__} 계약 불일치: {exc}") from exc
        try:
            mapped = legacy_mapper(raw)
            parsed = model.model_validate(mapped)
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            self.status.record_failure(elapsed, f"레거시 매핑 실패: {exc}")
            raise UpstreamError(f"{model.__name__} 매핑 실패: {exc}") from exc
        self.status.record_success(elapsed, detail="ok(legacy-mapped)")
        logger.info("%s: 레거시 응답 스키마를 계약으로 매핑했다", type(self).__name__)
        return parsed

    def post_model(
        self,
        path: str,
        payload: dict[str, Any],
        model: type[ModelT],
        legacy_mapper: Callable[[Any], dict[str, Any]] | None = None,
    ) -> ModelT:
        started = time.perf_counter()
        raw = self._request("POST", path, payload)
        return self._parse(raw, model, legacy_mapper, started)

    def get_model(
        self,
        path: str,
        model: type[ModelT],
        legacy_mapper: Callable[[Any], dict[str, Any]] | None = None,
    ) -> ModelT:
        started = time.perf_counter()
        raw = self._request("GET", path)
        return self._parse(raw, model, legacy_mapper, started)
