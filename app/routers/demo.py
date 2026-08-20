"""데모 시나리오 실행 엔드포인트 — 발표에서 버튼 하나로 재생한다.

`POST /demo/scenarios/{id}/run` 은 시나리오의 고정 입력으로 오케스트레이터를 태우고,
`expect` 블록 검증 결과까지 함께 돌려준다. 발표 직전 리허설에 그대로 쓴다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response

from app.config import FINGERPRINT_DIR
from app.demo import build_request, check_expectations, load_scenarios, pick_session
from app.services.orchestrator import Orchestrator, ProductNotFound
from app.store import get_store

router = APIRouter(tags=["Demo"])


@router.get("/demo/scenarios", summary="데모 시나리오 목록")
def scenarios() -> dict[str, Any]:
    items = load_scenarios()
    return {
        "total": len(items),
        "items": [
            {
                **s.as_dict(),
                "session_id": (lambda rec: rec.session_id if rec else None)(pick_session(s)),
            }
            for s in items.values()
        ],
    }


@router.post("/demo/scenarios/{scenario_id}/run", summary="시나리오 실행 + 기대값 검증")
def run_scenario(scenario_id: str, response: Response) -> dict[str, Any]:
    scenario = load_scenarios().get(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"시나리오를 찾을 수 없다: {scenario_id}")
    request = build_request(scenario)
    try:
        result = Orchestrator().advise(request)
    except ProductNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    problems = check_expectations(scenario, result)
    response.headers["X-Degraded"] = "true" if result.degraded else "false"
    response.headers["X-Demo-Check"] = "pass" if not problems else "fail"
    return {
        "scenario": scenario.as_dict(),
        "session_id": (lambda rec: rec.session_id if rec else None)(pick_session(scenario)),
        "response": result.model_dump(mode="json"),
        "check": {"passed": not problems, "problems": problems},
    }


@router.get("/demo/fingerprint-samples", summary="지문 등록 개체 샘플 (데모 화면용)")
def fingerprint_samples() -> dict[str, Any]:
    """`data/fingerprints/` 에 등록 이미지가 있는 시드 개체 목록.

    지문 매칭 데모 화면의 "등록 개체로 시연" 갤러리를 채운다. 이미지 `path` 는
    `POST /fingerprint/match` 의 `image_path` 로 그대로 쓸 수 있고, `url` 은
    화면 미리보기용(`/static/fingerprints/...`)이다. 시드에 없는 개체 폴더
    (구 6자리 규약 잔재 등)는 제외한다.
    """
    store = get_store()
    items: list[dict[str, Any]] = []
    if FINGERPRINT_DIR.exists():
        for asset_dir in sorted(FINGERPRINT_DIR.iterdir()):
            if not asset_dir.is_dir():
                continue
            asset = store.asset(asset_dir.name)
            if asset is None:
                continue
            images = [
                {
                    "path": f"data/fingerprints/{asset_dir.name}/{image.name}",
                    "url": f"/static/fingerprints/{asset_dir.name}/{image.name}",
                    "label": image.stem,
                }
                for image in sorted(asset_dir.iterdir())
                if image.suffix.lower() in {".jpg", ".jpeg", ".png"}
            ]
            if not images:
                continue
            owner = store.customer(asset.customer_id)
            items.append(
                {
                    "asset_id": asset.asset_id,
                    "product_name": asset.product_name,
                    "category": asset.category.value,
                    "condition_score": asset.condition_score,
                    "next_service_months": asset.next_service_months,
                    "headline_finding": asset.findings[0].note if asset.findings else None,
                    "customer_id": asset.customer_id,
                    "customer_name": owner.display_name if owner else None,
                    "tier": owner.tier.value if owner else None,
                    "images": images,
                }
            )
    return {"total": len(items), "items": items}
