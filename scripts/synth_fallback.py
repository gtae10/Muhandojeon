"""합성 폴백 — 외부 데이터셋이 하나도 없어도 파이프라인이 완주하게 한다.

설계 원칙: **우리 스키마를 두 번 구현하지 않는다.** 이 모듈은 외부 원본과 *같은 모양의
원시 입력*(styles.csv 형태 / H&M transactions 형태 / 클릭스트림 형태)만 만들고,
정규화·컨디션 계산·라벨링은 `build_catalog.py` / `build_customers.py` /
`build_sessions.py` 가 그대로 담당한다. 그래서 external 과 synth 의 결과 스키마가
어긋날 수 없다.

단독 실행하면 세 빌더 + export 를 synth 모드로 한 번에 돌린다.

    python -m scripts.synth_fallback            # 상품 40 / 고객 30 / 세션 60 전부 합성
    python -m scripts.synth_fallback --dry-run  # 생성될 원시 입력 규모만 출력

이벤트 어휘는 **실제 클릭스트림 데이터셋과 동일한 7종으로 제한**한다. 합성 데이터가 더
풍부해지면 external 경로에서만 필요한 규칙 합성이 검증되지 않기 때문이다.
"""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import IMAGES_DIR, get_settings

ROOT = Path(__file__).resolve().parents[1]

# 원본 클릭스트림과 동일한 이벤트 어휘
# (page_view / product_view / click / add_to_cart / purchase / login / logout)
RAW_EVENT_TYPES: tuple[str, ...] = (
    "page_view",
    "product_view",
    "click",
    "add_to_cart",
    "purchase",
    "login",
    "logout",
)

_GENDERS = ("Men", "Women", "Unisex")
_COLOURS = (
    "Black",
    "Brown",
    "Navy Blue",
    "Beige",
    "Grey",
    "White",
    "Tan",
    "Maroon",
    "Green",
    "Silver",
    "Gold",
    "Cream",
)
_SEASONS = ("Fall", "Winter", "Spring", "Summer")

#: (masterCategory, subCategory, articleType) 조합. app.domain.map_category 가 아는 값만 쓴다.
_SYNTH_TYPES: tuple[tuple[str, str, str], ...] = (
    ("Accessories", "Bags", "Handbags"),
    ("Accessories", "Bags", "Clutches"),
    ("Accessories", "Bags", "Messenger Bag"),
    ("Footwear", "Shoes", "Formal Shoes"),
    ("Footwear", "Shoes", "Casual Shoes"),
    ("Footwear", "Shoes", "Heels"),
    ("Accessories", "Watches", "Watches"),
    ("Accessories", "Belts", "Belts"),
    ("Accessories", "Wallets", "Wallets"),
)


def synth_style_rows(count: int = 160, seed: int = 42) -> list[dict[str, Any]]:
    """styles.csv 와 같은 컬럼 구성의 합성 상품 행."""
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for idx in range(count):
        master, sub, article = _SYNTH_TYPES[idx % len(_SYNTH_TYPES)]
        colour = rng.choice(_COLOURS)
        rows.append(
            {
                "id": 900000 + idx,
                "gender": rng.choice(_GENDERS),
                "masterCategory": master,
                "subCategory": sub,
                "articleType": article,
                "baseColour": colour,
                "season": rng.choice(_SEASONS),
                "year": rng.randint(2018, 2025),
                "usage": "Formal",
                "productDisplayName": f"{colour} {article} {900000 + idx}",
            }
        )
    return rows


def synth_transactions(
    n_customers: int = 240, seed: int = 42, article_ids: list[int] | None = None
) -> list[dict[str, Any]]:
    """H&M `transactions_train.csv` 와 같은 컬럼 구성(customer_id, article_id, t_dat, price)."""
    rng = random.Random(seed + 1)
    pool = article_ids or [900000 + i for i in range(160)]
    base = datetime(2018, 9, 20)
    rows: list[dict[str, Any]] = []
    for cidx in range(n_customers):
        customer_id = f"synthc{cidx:012d}{'0' * 40}"[:64]
        n_purchases = rng.choices(
            population=[1, 2, 3, 5, 7, 9, 12, 16, 21],
            weights=[6, 8, 14, 16, 14, 12, 10, 8, 4],
            k=1,
        )[0]
        for _ in range(n_purchases):
            day = rng.randint(0, 365 * 5)
            rows.append(
                {
                    "t_dat": (base + timedelta(days=day)).strftime("%Y-%m-%d"),
                    "customer_id": customer_id,
                    "article_id": rng.choice(pool),
                    "price": round(rng.uniform(0.01, 0.09), 6),
                    "sales_channel_id": rng.choice([1, 2]),
                }
            )
    rows.sort(key=lambda r: str(r["t_dat"]))
    return rows


def synth_clickstream(n_sessions: int = 400, seed: int = 42) -> list[dict[str, Any]]:
    """클릭스트림 원본과 같은 컬럼 구성(UserID, SessionID, Timestamp, EventType, ProductID, ...).

    원본과 동일하게 **이탈 세션(add_to_cart 있고 purchase 없음)** 이 절반 이상 나오도록 만든다.
    """
    rng = random.Random(seed + 2)
    base = datetime(2026, 3, 1)
    rows: list[dict[str, Any]] = []
    for sidx in range(n_sessions):
        user_id = 1000 + sidx % 250
        session_bucket = sidx % 10
        n_events = rng.randint(5, 14)
        abandons = rng.random() < 0.62
        ts = base + timedelta(days=rng.randint(0, 150), minutes=rng.randint(0, 600))
        events: list[str] = ["login", "page_view"]
        for _ in range(n_events):
            events.append(rng.choices(RAW_EVENT_TYPES[:4], weights=[3, 5, 3, 2], k=1)[0])
        events.append("add_to_cart")
        if not abandons:
            events.append("purchase")
        events.append("logout")
        for ev in events:
            ts = ts + timedelta(seconds=rng.randint(5, 240))
            product = f"prod_{rng.randint(1000, 9999)}" if ev not in {"login", "logout"} else ""
            amount = round(rng.uniform(40, 900), 2) if ev == "purchase" else ""
            rows.append(
                {
                    "UserID": user_id,
                    "SessionID": session_bucket,
                    "Timestamp": ts.strftime("%Y-%m-%d %H:%M:%S.%f"),
                    "EventType": ev,
                    "ProductID": product,
                    "Amount": amount,
                    "Outcome": "purchase" if ev == "purchase" else "",
                }
            )
    return rows


#: 카테고리별 플레이스홀더 색(RGB). 이미지 원본이 없을 때 카탈로그 화면이 비지 않게 한다.
PLACEHOLDER_COLORS: dict[str, tuple[int, int, int]] = {
    "BAG": (92, 64, 51),
    "SHOES": (38, 34, 32),
    "WATCH": (72, 78, 84),
    "BELT": (58, 44, 36),
    "WALLET": (108, 74, 58),
    "OUTERWEAR": (66, 70, 62),
    "ACCESSORY": (120, 96, 88),
}


def write_placeholder_image(category: str, dest: Path, size: tuple[int, int] = (300, 400)) -> None:
    """카테고리별 단색 플레이스홀더 이미지. Pillow 만 사용."""
    from PIL import Image, ImageDraw

    color = PLACEHOLDER_COLORS.get(category, (100, 100, 100))
    img = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 8, size[0] - 9, size[1] - 9], outline=(230, 226, 218), width=2)
    draw.text((16, size[1] - 28), category, fill=(240, 238, 232))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, quality=90)


def run_pipeline(dry_run: bool) -> int:
    """synth 모드로 빌더 전체를 실행한다."""
    settings = get_settings()
    steps = [
        [sys.executable, "-m", "scripts.build_catalog"],
        [sys.executable, "-m", "scripts.build_customers"],
        [sys.executable, "-m", "scripts.build_sessions"],
        [sys.executable, "-m", "scripts.export_for_team"],
    ]
    print("합성 폴백 파이프라인 (DATA_SOURCE=synth)")
    print(f"  원시 입력: 상품 {len(synth_style_rows())}행 / 거래 {len(synth_transactions())}행 / ")
    print(f"            클릭 {len(synth_clickstream())}행")
    print(f"  이미지 출력: {IMAGES_DIR.relative_to(ROOT)} (카테고리 단색 플레이스홀더)")
    print(f"  시드: {settings.seed}")
    if dry_run:
        print("  --dry-run → 실행하지 않고 종료")
        return 0
    env_note = "DATA_SOURCE=synth"
    for step in steps:
        print(f"\n$ {env_note} {' '.join(step[2:])}")
        proc = subprocess.run(  # noqa: S603 - 고정 커맨드
            step,
            cwd=ROOT,
            env={**_env_with_synth()},
            check=False,
        )
        if proc.returncode != 0:
            print(f"  ! 실패 (exit {proc.returncode})")
            return proc.returncode
    return 0


def _env_with_synth() -> dict[str, str]:
    import os

    env = dict(os.environ)
    env["DATA_SOURCE"] = "synth"
    return env


def main() -> int:
    ap = argparse.ArgumentParser(description="합성 데이터로 파이프라인 완주")
    ap.add_argument("--dry-run", action="store_true", help="규모만 출력하고 종료")
    args = ap.parse_args()
    return run_pipeline(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
