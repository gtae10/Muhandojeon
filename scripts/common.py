"""빌더 공용 유틸 — 고정 기준시각, id 포맷, provenance 기록, 원본 가용성 판정.

**기준시각을 고정하는 것이 이 파일의 핵심이다.** 컨디션 점수는 경과 연수로 계산되므로
`datetime.now()` 를 쓰면 매일 점수가 흔들리고 "컨디션 71점" 이라는 데모 대사가 깨진다.
그래서 `REFERENCE_NOW` 를 상수로 못박고, 필요하면 env `REFERENCE_NOW=2026-08-14T12:00:00+09:00`
로만 바꾼다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import PROCESSED_DIR, RAW_DIR, get_settings

KST = timezone(timedelta(hours=9))

_DEFAULT_REFERENCE_NOW = datetime(2026, 8, 14, 12, 0, 0, tzinfo=KST)


def reference_now() -> datetime:
    """모든 시간 계산의 기준시각(고정). env `REFERENCE_NOW` 로만 덮을 수 있다."""
    raw = os.environ.get("REFERENCE_NOW")
    if not raw:
        return _DEFAULT_REFERENCE_NOW
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        print(f"! REFERENCE_NOW 파싱 실패({raw}) → 기본값 사용")
        return _DEFAULT_REFERENCE_NOW
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)


REFERENCE_NOW = reference_now()

CATALOG_PATH = PROCESSED_DIR / "catalog_luxury.json"
CUSTOMERS_PATH = PROCESSED_DIR / "customers.json"
SESSIONS_PATH = PROCESSED_DIR / "sessions.json"
PROVENANCE_PATH = PROCESSED_DIR / "provenance.json"


def _env_path(var: str, default: Path) -> Path:
    """원본 경로를 env 로 덮을 수 있게 한다(다른 디스크에 내려둔 대용량 CSV 를 가리킬 때)."""
    raw = os.environ.get(var)
    return Path(raw).expanduser() if raw else default


STYLES_CSV = _env_path("STYLES_CSV_PATH", RAW_DIR / "fashion" / "styles.csv")
FASHION_IMAGES = _env_path("FASHION_IMAGES_PATH", RAW_DIR / "fashion" / "images")
HM_TRANSACTIONS = _env_path("HM_TRANSACTIONS_PATH", RAW_DIR / "hm" / "transactions_train.csv")
CLICKSTREAM_CSV = _env_path(
    "CLICKSTREAM_CSV_PATH", RAW_DIR / "clickstream" / "ecommerce_clickstream_transactions.csv"
)


def product_id(index: int) -> str:
    return f"LX-{index:04d}"


def customer_id(index: int) -> str:
    return f"CU-{index:04d}"


def asset_id(index: int) -> str:
    return f"AS-{index:06d}"


def session_id(index: int) -> str:
    return f"SE-{index:04d}"


@dataclass
class SourceDecision:
    """이 빌더가 원본을 썼는지 합성을 썼는지."""

    name: str
    external_path: Path
    used_external: bool
    reason: str
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return "external" if self.used_external else "synth"


def decide_source(name: str, path: Path) -> SourceDecision:
    """`DATA_SOURCE` 설정과 파일 존재 여부로 원본/합성을 판정한다.

    - `DATA_SOURCE=synth` → 무조건 합성 (원본이 있어도 무시)
    - `DATA_SOURCE=external` → 파일이 있으면 원본, 없으면 자동 합성 폴백
    """
    settings = get_settings()
    if settings.data_source == "synth":
        return SourceDecision(name, path, False, "DATA_SOURCE=synth (강제 합성)")
    if path.exists():
        size_mb = path.stat().st_size / 1e6
        return SourceDecision(
            name, path, True, f"원본 사용 ({size_mb:,.1f} MB)", {"size_mb": round(size_mb, 1)}
        )
    return SourceDecision(name, path, False, f"원본 없음 → 합성 폴백 ({path.name})")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def record_provenance(step: str, payload: dict[str, Any]) -> None:
    """빌드 단계별 출처 정보를 누적 기록한다. `docs/DATA_PROVENANCE.md` 생성 재료."""
    current: dict[str, Any] = {}
    if PROVENANCE_PATH.exists():
        try:
            loaded = read_json(PROVENANCE_PATH)
            if isinstance(loaded, dict):
                current = loaded
        except json.JSONDecodeError:
            current = {}
    current[step] = {
        "reference_now": REFERENCE_NOW.isoformat(),
        "seed": get_settings().seed,
        **payload,
    }
    write_json(PROVENANCE_PATH, current)


def banner(title: str) -> None:
    print(f"\n── {title} " + "─" * max(0, 56 - len(title)))
