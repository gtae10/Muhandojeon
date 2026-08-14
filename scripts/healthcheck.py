"""헬스 체크 — `make check` 의 마지막 단계.

서버를 따로 띄우지 않고 앱을 in-process 로 올려 `/health/detail` 과 핵심 엔드포인트를 실제로
호출한다. 데이터가 없거나 계약이 깨졌으면 여기서 exit 1 이 된다.

    python -m scripts.healthcheck
    python -m scripts.healthcheck --json     # 원본 JSON 출력
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from scripts.common import banner


def main() -> int:
    ap = argparse.ArgumentParser(description="in-process 헬스 체크")
    ap.add_argument("--json", action="store_true", help="원본 JSON 출력")
    args = ap.parse_args()

    banner("헬스 체크")
    problems: list[str] = []
    with TestClient(app) as client:
        detail: dict[str, Any] = client.get("/health/detail").json()
        if args.json:
            print(json.dumps(detail, ensure_ascii=False, indent=2))

        data = detail.get("data", {})
        print(f"  상태: {detail.get('status')}")
        print(
            f"  데이터: 상품 {data.get('products')} / 고객 {data.get('customers')} / "
            f"개체 {data.get('assets')} / 세션 {data.get('sessions')}"
        )
        for err in data.get("load_errors", []):
            problems.append(f"데이터 로드: {err}")

        for adapter in detail.get("adapters", []):
            print(
                f"    {adapter['module']:<12} {adapter['mode']:<6} {adapter['last_status']:<22} "
                f"{adapter['target'][:44]}"
            )

        llm = detail.get("llm", {})
        print(
            f"  LLM: {'연결' if llm.get('enabled') else '미연결(템플릿 폴백)'} / "
            f"캐시 {llm.get('cache_entries')}건"
        )
        demo = detail.get("demo", {})
        print(f"  데모: DEMO_MODE={demo.get('demo_mode')} / 시나리오 {demo.get('scenarios')}종")
        print(f"  DB: {detail.get('db')}")

        if data.get("products", 0) < 1:
            problems.append("상품이 없다 — `make data` 를 먼저 실행하라")
        if data.get("customers", 0) < 1:
            problems.append("고객이 없다 — `make data` 를 먼저 실행하라")

        # 핵심 엔드포인트 실제 호출
        checks: list[tuple[str, Any]] = [
            ("GET /catalog", client.get("/catalog")),
            ("GET /customers", client.get("/customers")),
            ("GET /lab/config", client.get("/lab/config")),
            ("GET /demo/scenarios", client.get("/demo/scenarios")),
        ]
        advise = client.post(
            "/session/advise",
            json={
                "customer_id": "CU-0001",
                "target_product_id": "LX-0001",
                "session_events": [],
                "strategy_id": "S2",
            },
        )
        checks.append(("POST /session/advise", advise))
        print("  엔드포인트")
        for name, res in checks:
            ok = res.status_code == 200
            print(f"    {'ok  ' if ok else 'FAIL'} {name} → {res.status_code}")
            if not ok:
                problems.append(f"{name} → {res.status_code} {res.text[:120]}")

        if advise.status_code == 200:
            body = advise.json()
            print(
                f"      인용 {body['cited_asset_ids']} / owned_assets_used="
                f"{body['owned_assets_used']} / X-Degraded={advise.headers.get('X-Degraded')}"
            )
            if not body["owned_assets_used"] and not body["no_assets"]:
                problems.append("S2 전략인데 소유 자산을 인용하지 않았다 (제품 차별점 실패 신호)")

    if problems:
        print("\n  문제")
        for problem in problems:
            print(f"    ! {problem}")
        return 1
    print("\n  모든 체크 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
