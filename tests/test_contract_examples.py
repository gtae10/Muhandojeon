"""계약 예시(`contracts/examples/*.json`)가 실제 시드로 그대로 실행 가능한지 검증.

예시에 시드에 없는 id 가 적히면 팀원이 그 payload 를 복사해 호출했을 때
`cited_asset_ids=[]` / `owned_assets_used=false` — 즉 제품 실패 신호가 나온다.
계약 문서가 팀 전체의 단일 출처이므로 예시도 실물이어야 한다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.data.provider import get_provider

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "contracts" / "examples"
ID_PATTERN = re.compile(r"\b(?:CU|LX|AS)-\d+\b")


def _seed_ids() -> set[str]:
    provider = get_provider()
    ids = {c.customer_id for c in provider.get_customers()}
    ids |= {p.product_id for p in provider.get_products()}
    ids |= {a.asset_id for a in provider.get_assets()}
    return ids


def _ids_in(value: object) -> set[str]:
    return set(ID_PATTERN.findall(json.dumps(value, ensure_ascii=False)))


@pytest.mark.parametrize("path", sorted(EXAMPLES_DIR.glob("*.json")), ids=lambda p: p.name)
def test_example_ids_exist_in_seed(path: Path) -> None:
    found = _ids_in(json.loads(path.read_text(encoding="utf-8")))
    unknown = sorted(found - _seed_ids())
    assert not unknown, f"{path.name}: 시드에 없는 id {unknown} — fixtures/ 의 실제 개체로 바꿀 것"
