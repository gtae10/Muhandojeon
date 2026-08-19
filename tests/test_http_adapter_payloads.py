"""HTTP 어댑터가 업스트림으로 **실제로 보내는 payload** 를 고정한다.

레거시 폴백 경로(`/api/chat`)는 계약 경로가 없는 백엔드에서만 타는데, 그때 보내는
필드가 백엔드 `ChatRequest`(user_id·session_id 필수)와 어긋나면 422 로 조용히 실패하고
데모가 `degraded=true` 로 떨어진다. 그 회귀를 여기서 막는다.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.adapters.clienteling import HttpClientelingAdapter
from contracts.clienteling import ClientelingReplyRequest


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.fixture
def example_request() -> ClientelingReplyRequest:
    example = ClientelingReplyRequest.model_config["json_schema_extra"]["example"]  # type: ignore[index]
    return ClientelingReplyRequest.model_validate(example)


def test_legacy_chat_payload_has_backend_required_fields(
    monkeypatch: pytest.MonkeyPatch, example_request: ClientelingReplyRequest
) -> None:
    """계약 경로가 없는 백엔드 → `/api/chat` 폴백 시 user_id/session_id 를 반드시 보낸다."""
    sent: list[tuple[str, dict[str, Any]]] = []

    def fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        payload = kwargs.get("json") or {}
        sent.append((url, payload))
        if url.endswith("/clienteling/reply"):
            raise httpx.ConnectError("계약 엔드포인트 없음")
        return _FakeResponse({"session_id": "s1", "reply": "안내드립니다.", "model_used": "gpt-4o"})

    monkeypatch.setattr(httpx, "request", fake_request)

    reply = HttpClientelingAdapter().reply(example_request)

    assert [url.rsplit("/", 1)[-1] for url, _ in sent][-1] == "chat"
    legacy_payload = sent[-1][1]
    # 백엔드 backend/app/schemas/models.py 의 ChatRequest 필수 필드
    for field in ("user_id", "session_id", "message"):
        assert field in legacy_payload, f"레거시 payload 에 {field} 누락 → 백엔드가 422 를 낸다"
    assert legacy_payload["user_id"] == example_request.customer_id
    assert reply.message
