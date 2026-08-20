"""어댑터 Protocol 과 상태 추적.

모듈마다 `Mock*Adapter` / `Http*Adapter` 두 구현이 **같은 Protocol** 을 만족한다.
팀원 모듈이 완성되는 순서가 다르므로 모듈별로 하나씩 전환할 수 있어야 한다
(`ADAPTER_MODE` 전역 + `INTENT_ADAPTER` 등 모듈별 오버라이드).

여기서 과도한 추상화는 하지 않는다. 다만 **전환 지점**은 확실히 분리한다.
`AdapterStatus` 는 `/health/detail` 이 "발표 직전 5초 점검"으로 쓸 수 있게 최근 호출 결과를 남긴다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from contracts.assets import CustomerAssetsResponse
from contracts.clienteling import (
    ClientelingOutreachRequest,
    ClientelingOutreachResponse,
    ClientelingReplyRequest,
    ClientelingReplyResponse,
)
from contracts.condition import ConditionScoreRequest, ConditionScoreResponse
from contracts.fingerprint import FingerprintMatchRequest, FingerprintMatchResponse
from contracts.intent import IntentClassifyRequest, IntentClassifyResponse


class UpstreamError(RuntimeError):
    """업스트림(팀원 모듈) 호출 실패. 오케스트레이터가 폴백으로 흡수한다."""


@dataclass
class AdapterStatus:
    """어댑터 1개의 최근 상태. 헬스 대시보드에 그대로 노출된다."""

    name: str
    module: str
    mode: str
    target: str = ""
    calls: int = 0
    failures: int = 0
    last_status: str = "unused"
    last_latency_ms: float | None = None
    last_error: str | None = None
    last_called_at: float | None = None

    def record_success(self, latency_ms: float, detail: str = "ok") -> None:
        self.calls += 1
        self.last_status = detail
        self.last_latency_ms = round(latency_ms, 2)
        self.last_called_at = time.time()
        self.last_error = None

    def record_failure(self, latency_ms: float, error: str) -> None:
        self.calls += 1
        self.failures += 1
        self.last_status = "error"
        self.last_latency_ms = round(latency_ms, 2)
        self.last_called_at = time.time()
        self.last_error = error[:300]

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "module": self.module,
            "mode": self.mode,
            "target": self.target,
            "calls": self.calls,
            "failures": self.failures,
            "last_status": self.last_status,
            "last_latency_ms": self.last_latency_ms,
            "last_error": self.last_error,
        }


@dataclass
class AdapterBase:
    """상태 추적을 공유하는 최소 베이스."""

    module: str
    mode: str
    target: str = ""
    status: AdapterStatus = field(init=False)

    def __post_init__(self) -> None:
        self.status = AdapterStatus(
            name=type(self).__name__, module=self.module, mode=self.mode, target=self.target
        )


@runtime_checkable
class IntentPort(Protocol):
    """AI1 — 인텐트/망설임 분류."""

    status: AdapterStatus

    def classify(self, request: IntentClassifyRequest) -> IntentClassifyResponse: ...


@runtime_checkable
class ClientelingPort(Protocol):
    """AI2 — 클라이언텔링 상담."""

    status: AdapterStatus

    def reply(self, request: ClientelingReplyRequest) -> ClientelingReplyResponse: ...

    def outreach(self, request: ClientelingOutreachRequest) -> ClientelingOutreachResponse: ...


@runtime_checkable
class AssetPort(Protocol):
    """백엔드 — 소유 개체 조회."""

    status: AdapterStatus

    def assets(self, customer_id: str) -> CustomerAssetsResponse: ...


@runtime_checkable
class FingerprintPort(Protocol):
    """백엔드 — 개체 지문 매칭."""

    status: AdapterStatus

    def match(self, request: FingerprintMatchRequest) -> FingerprintMatchResponse: ...


@runtime_checkable
class ConditionPort(Protocol):
    """백엔드 — 컨디션 점수."""

    status: AdapterStatus

    def score(self, request: ConditionScoreRequest) -> ConditionScoreResponse: ...
