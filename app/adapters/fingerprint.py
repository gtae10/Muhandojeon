"""개체 지문 매칭 어댑터 (백엔드).

목 구현은 임베딩을 만들지 않는다(그건 백엔드 담당 몫이고, 대회 API 에는 비전 모델이 없다).
대신 **경로 규약과 시드 개체 목록**으로 판정한다.

1. 경로가 `data/fingerprints/{asset_id}/...` 규약을 따르고 그 개체가 시드에 있으면 매칭(0.9+)
2. 아니면 후보를 유사도 낮은 값으로 돌려주고 `is_match=false`

유사도는 경로 해시 기반 결정적 값이다. 데모가 매번 달라지지 않게 하려는 의도이며, 실제 임베딩
유사도가 아니라는 점은 `/health/detail` 의 target 표시와 문서에 남긴다.
"""

from __future__ import annotations

import re
import time
from typing import Any

from app.adapters.base import AdapterBase
from app.adapters.http_base import HttpAdapterBase
from app.domain import stable_hash
from app.store import DataStore, get_store
from contracts.fingerprint import (
    FingerprintCandidate,
    FingerprintMatchRequest,
    FingerprintMatchResponse,
)

MATCH_THRESHOLD = 0.75
# 경로 규약의 개체 id. 시드는 4자리(AS-0001), 데이터셋 계열 예시는 6자리다.
ASSET_ID_RE = re.compile(r"(AS-\d{4,6})")


class MockFingerprintAdapter(AdapterBase):
    """등록 기록 + 경로 규약 기반 매칭."""

    def __init__(self, store: DataStore | None = None) -> None:
        super().__init__(module="fingerprint", mode="mock", target="경로 규약 + 시드 개체 목록")
        self.store = store or get_store()

    def match(self, request: FingerprintMatchRequest) -> FingerprintMatchResponse:
        started = time.perf_counter()
        key = request.image_path or (request.image_base64 or "")[:64]

        matched: str | None = None
        similarity = 0.0
        detail = ""

        found = ASSET_ID_RE.search(key)
        if found and self.store.asset(found.group(1)) is not None:
            matched = found.group(1)
            similarity = 0.90 + (stable_hash("sim", key) % 60) / 1000.0
            detail = "경로 규약 일치"

        pool = (
            self.store.customer_assets(request.customer_id)
            if request.customer_id
            else list(self.store.assets.values())
        )
        candidates: list[FingerprintCandidate] = []
        if matched:
            candidates.append(
                FingerprintCandidate(asset_id=matched, similarity=round(similarity, 3))
            )
        for asset in pool:
            if asset.asset_id == matched:
                continue
            score = 0.15 + (stable_hash("cand", key, asset.asset_id) % 450) / 1000.0
            candidates.append(
                FingerprintCandidate(asset_id=asset.asset_id, similarity=round(score, 3))
            )
        candidates.sort(key=lambda c: -c.similarity)
        candidates = candidates[: request.top_k]

        if matched is None and candidates:
            similarity = candidates[0].similarity
            detail = "임계 미달 — 미등록 개체로 판단"

        elapsed = (time.perf_counter() - started) * 1000
        is_match = matched is not None and similarity >= MATCH_THRESHOLD
        self.status.record_success(
            elapsed, f"{'match' if is_match else 'no-match'} ({similarity:.2f}) {detail}".strip()
        )
        return FingerprintMatchResponse(
            matched_asset_id=matched if is_match else None,
            similarity=round(min(1.0, similarity), 3),
            is_match=is_match,
            candidates=candidates,
            threshold=MATCH_THRESHOLD,
        )


def legacy_fingerprint_mapper(raw: Any) -> dict[str, Any]:
    """팀 백엔드의 `POST /api/fingerprint` 응답을 계약으로 옮긴다.

    그 응답에는 유사도가 없고 `is_new_registration` 만 있다. 최초 등록이면 매칭 실패로 본다.
    """
    if not isinstance(raw, dict):
        raise TypeError(f"dict 가 아님: {type(raw)}")
    asset_id = raw.get("matched_asset_id") or raw.get("asset_id")
    is_new = bool(raw.get("is_new_registration", False))
    similarity = raw.get("similarity")
    if similarity is None:
        similarity = 0.0 if is_new else 0.9
    similarity = max(0.0, min(1.0, float(similarity)))
    threshold = float(raw.get("threshold", MATCH_THRESHOLD))
    is_match = bool(raw.get("is_match", (not is_new) and similarity >= threshold))
    return {
        "matched_asset_id": str(asset_id) if (asset_id and is_match) else None,
        "similarity": similarity,
        "is_match": is_match,
        "candidates": raw.get("candidates")
        or ([] if not asset_id else [{"asset_id": str(asset_id), "similarity": similarity}]),
        "threshold": threshold,
    }


class HttpFingerprintAdapter(HttpAdapterBase):
    """실제 백엔드 호출 (`FINGERPRINT_BASE_URL`)."""

    def __init__(self) -> None:
        super().__init__(module="fingerprint")

    def match(self, request: FingerprintMatchRequest) -> FingerprintMatchResponse:
        return self.post_model(
            "/fingerprint/match",
            request.model_dump(mode="json"),
            FingerprintMatchResponse,
            legacy_mapper=legacy_fingerprint_mapper,
        )
