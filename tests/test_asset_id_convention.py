"""개체 id 자릿수 규약이 코드 전체에서 시드와 일치하는지 고정.

시드 개체 id 는 4자리(`AS-0001`)인데 초기 문서 예시가 6자리(`AS-000031`)여서
정규식이 6자리만 받도록 굳어 있었다. 그 상태에서는
  - 지문 매칭이 실제 경로(`data/fingerprints/AS-0001/...`)를 한 건도 못 잡고
  - 상담 응답 본문의 개체 id 회수가 항상 0건이 되어 `owned_assets_used=false` 가 된다.
둘 다 조용히 실패해서 눈에 안 띈다. 그래서 여기서 못 박는다.
"""

from __future__ import annotations

from app.adapters.clienteling import legacy_clienteling_mapper
from app.adapters.fingerprint import MockFingerprintAdapter
from app.store import get_store
from contracts.clienteling import ClientelingReplyResponse
from contracts.fingerprint import FingerprintMatchRequest


def test_seed_asset_ids_are_four_digit() -> None:
    """시드가 4자리 규약을 유지하는지 (바뀌면 아래 두 테스트의 전제가 깨진다)."""
    ids = [a.asset_id for a in get_store().customer_assets("CU-0001")]
    assert ids, "CU-0001 의 개체가 없다"
    assert all(len(aid.split("-")[1]) == 4 for aid in ids), ids


def test_mock_fingerprint_matches_seed_path() -> None:
    """경로 규약의 실제 시드 id 를 매칭한다."""
    adapter = MockFingerprintAdapter()
    result = adapter.match(
        FingerprintMatchRequest(image_path="data/fingerprints/AS-0001/handle_01.jpg", top_k=3)
    )
    assert result.matched_asset_id == "AS-0001"
    assert result.is_match is True


def test_mock_fingerprint_rejects_unknown_asset() -> None:
    """시드에 없는 개체 id 는 매칭으로 치지 않는다."""
    adapter = MockFingerprintAdapter()
    result = adapter.match(
        FingerprintMatchRequest(image_path="data/fingerprints/AS-999999/handle_01.jpg", top_k=3)
    )
    assert result.matched_asset_id is None
    assert result.is_match is False


def test_legacy_reply_recovers_four_digit_id() -> None:
    """cited_asset_ids 가 빈 레거시 응답에서 본문의 4자리 id 를 회수한다."""
    raw = {"reply": "보유하신 AS-0001 의 컨디션은 71점입니다.", "session_id": "s1"}
    mapped = ClientelingReplyResponse.model_validate(legacy_clienteling_mapper(raw))
    assert mapped.cited_asset_ids == ["AS-0001"]
