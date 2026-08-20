"""지문 매칭 데모 화면의 데이터 계약 고정.

프론트 `/fingerprint` 화면은 `GET /demo/fingerprint-samples` 로 갤러리를 채우고,
그 `path` 를 그대로 `POST /fingerprint/match` 에 넣어 시연한다. 이 왕복이 깨지면
발표의 "개체 식별" 장면이 통째로 빈다. 여기서 못 박는다.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_samples_only_include_seed_assets() -> None:
    """시드에 있는 개체만 나온다 — 구 6자리 규약 폴더(AS-000001)는 제외."""
    with TestClient(app) as client:
        body = client.get("/demo/fingerprint-samples").json()
    ids = [item["asset_id"] for item in body["items"]]
    assert "AS-0001" in ids, ids
    assert all(len(aid.split("-")[1]) == 4 for aid in ids), ids


def test_samples_carry_owner_and_condition_meta() -> None:
    """화면이 개체→고객 역추적 카드를 그릴 수 있는 메타가 실려 있다."""
    with TestClient(app) as client:
        body = client.get("/demo/fingerprint-samples").json()
    item = next(i for i in body["items"] if i["asset_id"] == "AS-0001")
    assert item["customer_id"] == "CU-0001"
    assert item["customer_name"]
    assert item["product_name"] == "Aurelia Top Handle"
    assert item["condition_score"] == 71  # 데모 전제 (fixtures 불변식)
    assert item["images"], "등록 이미지가 비어 있다"


def test_sample_image_is_served_and_matches() -> None:
    """샘플 이미지 미리보기(url)와 매칭 질의(path)가 실제로 왕복한다."""
    with TestClient(app) as client:
        body = client.get("/demo/fingerprint-samples").json()
        image = body["items"][0]["images"][0]

        preview = client.get(image["url"])
        assert preview.status_code == 200
        assert preview.headers["content-type"].startswith("image/")

        match = client.post(
            "/fingerprint/match", json={"image_path": image["path"], "top_k": 3}
        ).json()
        assert match["is_match"] is True
        assert match["matched_asset_id"] == body["items"][0]["asset_id"]


def test_unregistered_query_is_not_a_match() -> None:
    """미등록 질의(경로 규약 밖)는 미매칭 — 화면의 '신규 등록 제안' 분기 전제."""
    with TestClient(app) as client:
        match = client.post(
            "/fingerprint/match", json={"image_base64": "aGVsbG8=", "top_k": 3}
        ).json()
    assert match["is_match"] is False
    assert match["matched_asset_id"] is None
