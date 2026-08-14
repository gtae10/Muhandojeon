"""상품 카탈로그 구축 — Fashion Product Images(styles.csv) → 럭셔리 톤 40개 카탈로그.

원본 상품명을 그대로 쓰면 발표 화면에 "Navy Blue Casual Shoes 9,900원" 같은 것이 뜨고
럭셔리 서사가 그 자리에서 무너진다. 그래서 LLM 으로 한 번 리라이팅한다.
LLM 키가 없거나 호출이 실패하면 **결정적 템플릿 리라이터**가 같은 스키마로 채운다.

    python -m scripts.build_catalog             # 기존 파일 있으면 그대로 두고 종료
    python -m scripts.build_catalog --force     # 재생성 (발표 대본이 깨질 수 있음)
    python -m scripts.build_catalog --dry-run   # 선별 결과만 출력

**결과는 `data/processed/catalog_luxury.json` 에 고정된다.** 데모마다 상품명이 바뀌면
발표 대본이 깨지므로 `--force` 없이는 절대 덮어쓰지 않는다.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import IMAGES_DIR, PROCESSED_DIR, get_settings
from app.domain import (
    AVAILABLE_SIZES,
    CARE_NOTES,
    CATEGORY_NOUNS,
    COLLECTIONS,
    LINES,
    MATERIALS,
    PRICE_BANDS,
    SIZE_SYSTEMS,
    deterministic_price,
    map_category,
    pick,
    stable_hash,
)
from app.llm import Message, get_llm
from contracts.common import Product, ProductCategory
from scripts.common import (
    CATALOG_PATH,
    FASHION_IMAGES,
    STYLES_CSV,
    banner,
    decide_source,
    product_id,
    read_json,
    record_provenance,
    write_json,
)
from scripts.synth_fallback import synth_style_rows, write_placeholder_image

#: 카테고리별 선별 수량. 합계 40.
QUOTA: dict[ProductCategory, int] = {
    ProductCategory.BAG: 12,
    ProductCategory.SHOES: 12,
    ProductCategory.WATCH: 8,
    ProductCategory.WALLET: 4,
    ProductCategory.BELT: 4,
}

#: 선별 우선 articleType. 화면에 뜰 이미지 톤을 맞추기 위한 큐레이션이다.
#: (백팩·트롤리·스니커즈는 럭셔리 서사와 어긋나므로 후순위. 후보가 부족할 때만 쓰인다.)
PREFERRED_ARTICLE_TYPES: dict[ProductCategory, frozenset[str]] = {
    ProductCategory.BAG: frozenset({"handbags", "clutches", "tote bag"}),
    ProductCategory.SHOES: frozenset({"formal shoes", "heels", "flats", "boots"}),
    ProductCategory.WATCH: frozenset({"watches"}),
    ProductCategory.WALLET: frozenset({"wallets", "clutch wallet", "card holder"}),
    ProductCategory.BELT: frozenset({"belts"}),
}

#: 원본 baseColour → 럭셔리 컬러명.
COLOR_MAP: dict[str, str] = {
    "black": "Noir",
    "brown": "Cognac",
    "navy blue": "Bleu Nuit",
    "blue": "Bleu Orage",
    "beige": "Sable",
    "grey": "Étain",
    "white": "Craie",
    "off white": "Craie",
    "tan": "Fauve",
    "maroon": "Bordeaux",
    "red": "Rouge Profond",
    "green": "Vert Cyprès",
    "olive": "Vert Kaki",
    "silver": "Argent",
    "gold": "Doré",
    "cream": "Ivoire",
    "pink": "Rose Poudré",
    "purple": "Prune",
    "yellow": "Ambre",
    "orange": "Abricot",
    "khaki": "Kaki",
    "charcoal": "Anthracite",
    "burgundy": "Bordeaux",
    "copper": "Cuivre",
    "bronze": "Bronze",
    "steel": "Acier",
    "taupe": "Taupe",
    "nude": "Nu",
    "mushroom brown": "Champignon",
    "coffee brown": "Moka",
    "magenta": "Fuchsia Profond",
    "teal": "Bleu Céladon",
    "turquoise blue": "Turquoise",
    "sea green": "Vert d'Eau",
    "rust": "Rouille",
    "peach": "Pêche",
    "mauve": "Mauve Cendré",
    "lavender": "Lavande",
    "mustard": "Moutarde",
    "multi": "Mosaïque",
    "metallic": "Métallisé",
    "grey melange": "Étain Chiné",
    "rose": "Rose Ancien",
    "skin": "Nu",
    "navy": "Bleu Nuit",
}


@dataclass
class StyleRow:
    """원본(또는 합성) 상품 1행 중 우리가 쓰는 필드만."""

    raw_id: str
    category: ProductCategory
    base_colour: str
    article_type: str
    season: str
    year: int
    gender: str
    display_name: str
    image_src: Path | None


def load_style_rows() -> tuple[list[StyleRow], str, dict[str, Any]]:
    """원본 styles.csv 또는 합성 행을 읽어 StyleRow 목록으로 만든다."""
    decision = decide_source("catalog", STYLES_CSV)
    print(f"  소스: {decision.label} — {decision.reason}")

    raw_rows: list[dict[str, Any]]
    if decision.used_external:
        import polars as pl

        frame = pl.read_csv(
            STYLES_CSV,
            truncate_ragged_lines=True,
            ignore_errors=True,
        )
        raw_rows = frame.to_dicts()
        images = (
            {p.stem: p for p in FASHION_IMAGES.glob("*.jpg")} if FASHION_IMAGES.exists() else {}
        )
    else:
        raw_rows = synth_style_rows(seed=get_settings().seed)
        images = {}

    rows: list[StyleRow] = []
    for raw in raw_rows:
        category = map_category(
            str(raw.get("subCategory") or ""), str(raw.get("articleType") or "")
        )
        if category is None or category not in QUOTA:
            continue
        raw_id = str(raw.get("id"))
        rows.append(
            StyleRow(
                raw_id=raw_id,
                category=category,
                base_colour=str(raw.get("baseColour") or "Black"),
                article_type=str(raw.get("articleType") or ""),
                season=str(raw.get("season") or ""),
                year=int(raw.get("year") or 2020),
                gender=str(raw.get("gender") or "Unisex"),
                display_name=str(raw.get("productDisplayName") or ""),
                image_src=images.get(raw_id),
            )
        )
    meta = {
        "source": decision.label,
        "reason": decision.reason,
        "candidate_rows": len(rows),
        "styles_csv_rows": len(raw_rows),
    }
    return rows, decision.label, meta


def select_rows(rows: list[StyleRow]) -> list[StyleRow]:
    """카테고리 쿼터에 맞춰 결정적으로 40개를 고른다.

    후보가 쿼터보다 적으면 남는 몫을 다른 카테고리로 재분배하고 그 사실을 출력한다
    (조용히 40개 미만으로 끝나지 않게).
    """
    # 이미지가 없는 행도 후보로 둔다(플레이스홀더로 대체되므로 카탈로그가 비지 않는다).
    # 큐레이션 우선순위: 선호 articleType 을 앞에, 나머지를 뒤에 붙인다.
    by_cat: dict[ProductCategory, list[StyleRow]] = {c: [] for c in QUOTA}
    fallback_cat: dict[ProductCategory, list[StyleRow]] = {c: [] for c in QUOTA}
    for row in rows:
        preferred = PREFERRED_ARTICLE_TYPES.get(row.category, frozenset())
        target = by_cat if row.article_type.strip().lower() in preferred else fallback_cat
        target[row.category].append(row)

    for cat, items in by_cat.items():
        items.sort(key=lambda r: stable_hash("select", r.raw_id))
        fallback_cat[cat].sort(key=lambda r: stable_hash("select", r.raw_id))
        if len(items) < QUOTA[cat]:
            print(
                f"  ! {cat.value} 선호 후보 {len(items)}개 < 쿼터 {QUOTA[cat]}개 "
                f"→ 비선호 {len(fallback_cat[cat])}개에서 보충"
            )
            items.extend(fallback_cat[cat])

    chosen: list[StyleRow] = []
    shortfall = 0
    for cat in QUOTA:
        take = min(QUOTA[cat], len(by_cat[cat]))
        chosen.extend(by_cat[cat][:take])
        shortfall += QUOTA[cat] - take

    if shortfall:
        print(f"  부족분 {shortfall}개를 후보가 남은 카테고리에서 보충한다")
        for cat in QUOTA:
            pool = by_cat[cat][QUOTA[cat] :]
            while shortfall and pool:
                chosen.append(pool.pop(0))
                shortfall -= 1

    # 카테고리 순서를 섞어 화면이 카테고리별로 뭉치지 않게 하되, 순서 자체는 결정적으로.
    chosen.sort(key=lambda r: stable_hash("order", r.raw_id))
    return chosen


def luxury_color(base_colour: str) -> str:
    return COLOR_MAP.get(base_colour.strip().lower(), base_colour.strip().title())


def template_item(row: StyleRow, pid: str) -> dict[str, Any]:
    """LLM 없이도 럭셔리 톤을 맞추는 결정적 리라이터."""
    line = pick(LINES, "line", row.raw_id)
    noun = pick(CATEGORY_NOUNS[row.category], "noun", row.raw_id)
    return {
        "product_id": pid,
        "name": f"{line} {noun}",
        "category": row.category.value,
        "collection": pick(COLLECTIONS, "collection", row.raw_id),
        "material": pick(MATERIALS[row.category], "material", row.raw_id),
        "color": luxury_color(row.base_colour),
        "price_krw": deterministic_price(row.category, row.raw_id),
        "size_system": size_system_for(row, line),
        "available_sizes": available_sizes_for(row),
        "care_notes": CARE_NOTES[row.category],
        "rewriter": "template",
    }


def size_system_for(row: StyleRow, line: str) -> str:
    base = SIZE_SYSTEMS[row.category]
    if row.category is ProductCategory.SHOES:
        return f"{base} / Last: {line}"
    return base


def available_sizes_for(row: StyleRow) -> list[str]:
    """재고 사이즈를 결정적으로 줄인다.

    일부 상품은 희소 재고 상태로 만들어 재고 상담 시나리오가 성립하게 한다.
    """
    sizes = list(AVAILABLE_SIZES[row.category])
    if len(sizes) <= 1:
        return sizes
    seed = stable_hash("stock", row.raw_id)
    if seed % 7 == 0:  # 희소 재고
        keep = 1
    elif seed % 3 == 0:
        keep = max(2, len(sizes) // 3)
    else:
        keep = max(2, len(sizes) - 2)
    step = max(1, len(sizes) // keep)
    return sizes[::step][:keep]


def llm_rewrite(rows: list[tuple[str, StyleRow]]) -> dict[str, dict[str, Any]]:
    """LLM 배치 리라이팅. 실패/누락 항목은 호출자가 템플릿으로 채운다."""
    llm = get_llm()
    out: dict[str, dict[str, Any]] = {}
    batch_size = 8
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        payload = [
            {
                "product_id": pid,
                "category": row.category.value,
                "original_type": row.article_type,
                "original_color": row.base_colour,
                "season": row.season,
                "year": row.year,
                "gender": row.gender,
                "price_min_krw": PRICE_BANDS[row.category][0],
                "price_max_krw": PRICE_BANDS[row.category][1],
            }
            for pid, row in batch
        ]
        messages: list[Message] = [
            {
                "role": "system",
                "content": (
                    "당신은 럭셔리 메종의 시니어 카피라이터다. 주어진 상품 속성을 근거로 "
                    "가상의 하이엔드 제품 정보를 만든다.\n"
                    "규칙:\n"
                    "1. 실존 브랜드명·상표를 절대 쓰지 않는다(가상의 라인명만).\n"
                    "2. 제품명은 '라인명 + 형태'의 2~3단어 영문 (예: Aurelia Derby).\n"
                    "3. material 은 한국어로 소재·제법을 구체적으로 "
                    "(예: '박스카프 카프스킨 / 굿이어 웰트').\n"
                    "4. price_krw 는 주어진 min~max 범위 안의 10만원 단위 정수.\n"
                    "5. 과장 광고 표현('세계 최고' 등)을 쓰지 않는다.\n"
                    "JSON 배열만 출력한다. 설명 문장을 덧붙이지 않는다."
                ),
            },
            {
                "role": "user",
                "content": (
                    "다음 상품들을 리라이팅하라. 각 항목에 대해 "
                    '{"product_id","name","collection","material","color","price_krw"} '
                    "키를 가진 객체를 만들어 JSON 배열로 반환하라.\n"
                    f"{payload}"
                ),
            },
        ]
        parsed = llm.complete_json(messages, fallback=lambda: [], cache=True, max_tokens=1600)
        if not isinstance(parsed, list):
            continue
        for item in parsed:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("product_id", ""))
            if pid:
                out[pid] = item
    return out


def merge_item(row: StyleRow, pid: str, llm_item: dict[str, Any] | None) -> dict[str, Any]:
    """LLM 결과를 검증해 템플릿 위에 덮는다. 이상값은 템플릿 값을 유지한다."""
    item = template_item(row, pid)
    if not llm_item:
        return item

    low, high = PRICE_BANDS[row.category]
    name = str(llm_item.get("name") or "").strip()
    if name and 2 <= len(name) <= 40:
        item["name"] = name
    for key in ("collection", "material", "color"):
        val = str(llm_item.get(key) or "").strip()
        if val and len(val) <= 80:
            item[key] = val
    try:
        price = int(llm_item.get("price_krw") or 0)
    except (TypeError, ValueError):
        price = 0
    if low <= price <= high:
        item["price_krw"] = price - price % 100_000
    item["rewriter"] = "llm"
    return item


def dedupe_names(items: list[dict[str, Any]]) -> None:
    """제품명 충돌 제거. 같은 이름이면 라인명을 다음 후보로 회전한다."""
    seen: set[str] = set()
    for item in items:
        name = str(item["name"])
        if name not in seen:
            seen.add(name)
            continue
        parts = name.split(" ", 1)
        suffix = parts[1] if len(parts) > 1 else ""
        for offset in range(1, len(LINES) + 1):
            base_idx = stable_hash("line", str(item["product_id"])) % len(LINES)
            candidate = f"{LINES[(base_idx + offset) % len(LINES)]} {suffix}".strip()
            if candidate not in seen:
                item["name"] = candidate
                seen.add(candidate)
                break


def copy_image(row: StyleRow, pid: str) -> tuple[str, list[int]]:
    """원본 이미지를 `data/processed/images/{product_id}.jpg` 로 복사(없으면 플레이스홀더).

    원본(small 버전)은 60x80 저해상도다. 인위적 업스케일은 오히려 흐려 보이므로 그대로 두고
    실제 해상도를 카탈로그에 기록해 프론트가 렌더 크기를 정하게 한다.
    """
    from PIL import Image

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    dest = IMAGES_DIR / f"{pid}.jpg"
    if row.image_src and row.image_src.exists():
        shutil.copyfile(row.image_src, dest)
    else:
        write_placeholder_image(row.category.value, dest)
    with Image.open(dest) as img:
        size = [img.width, img.height]
    return f"images/{dest.name}", size


def main() -> int:
    ap = argparse.ArgumentParser(description="럭셔리 카탈로그 40개 구축")
    ap.add_argument("--force", action="store_true", help="기존 카탈로그를 덮어쓴다")
    ap.add_argument("--dry-run", action="store_true", help="선별 결과만 출력")
    args = ap.parse_args()

    banner("카탈로그 구축")
    if CATALOG_PATH.exists() and not args.force and not args.dry_run:
        existing = len(read_json(CATALOG_PATH).get("items", []))
        print(
            f"  이미 존재: {CATALOG_PATH.relative_to(PROCESSED_DIR.parent.parent)} ({existing}개)"
        )
        print("  → 상품명이 바뀌면 발표 대본이 깨진다. 재생성하려면 --force")
        return 0

    rows, source_label, meta = load_style_rows()
    chosen = select_rows(rows)
    print(f"  후보 {len(rows)}개 → 선별 {len(chosen)}개")
    counts: dict[str, int] = {}
    for row in chosen:
        counts[row.category.value] = counts.get(row.category.value, 0) + 1
    print(f"  카테고리 분포: {counts}")

    if args.dry_run:
        for idx, row in enumerate(chosen[:10], start=1):
            print(f"    {product_id(idx)} {row.category.value:<7} {row.display_name[:48]}")
        print("  --dry-run → 파일을 쓰지 않고 종료")
        return 0

    pairs = [(product_id(idx), row) for idx, row in enumerate(chosen, start=1)]
    llm = get_llm()
    llm_items = llm_rewrite(pairs) if llm.settings.llm_enabled else {}
    if not llm_items:
        print("  LLM 리라이팅 결과 없음 → 결정적 템플릿 리라이터 사용")

    items: list[dict[str, Any]] = []
    for pid, row in pairs:
        item = merge_item(row, pid, llm_items.get(pid))
        image_path, image_px = copy_image(row, pid)
        item["image_path"] = image_path
        item["source"] = {
            "dataset": "fashion-product-images-small" if source_label == "external" else "synth",
            "image_px": image_px,
            "raw_id": row.raw_id,
            "raw_article_type": row.article_type,
            "raw_base_colour": row.base_colour,
            "raw_display_name": row.display_name,
            "raw_year": row.year,
        }
        items.append(item)
    dedupe_names(items)

    # 계약(Product)으로 검증해 스키마 어긋남을 여기서 잡는다.
    validated = [Product.model_validate(item) for item in items]
    rewriters = {i["rewriter"] for i in items}
    payload = {
        "generated_with": {
            "source": source_label,
            "rewriter": sorted(rewriters),
            "llm_model": llm.settings.llm_model if llm.settings.llm_enabled else None,
            "quota": {k.value: v for k, v in QUOTA.items()},
        },
        "items": items,
    }
    write_json(CATALOG_PATH, payload)
    record_provenance(
        "catalog",
        {
            **meta,
            "selected": len(validated),
            "rewriter": sorted(rewriters),
            "images_dir": str(IMAGES_DIR.relative_to(PROCESSED_DIR.parent.parent)),
        },
    )
    print(f"  저장: {CATALOG_PATH.relative_to(PROCESSED_DIR.parent.parent)} ({len(validated)}개)")
    print(f"  이미지: {IMAGES_DIR.relative_to(PROCESSED_DIR.parent.parent)}/*.jpg")
    sample = validated[:3]
    for prod in sample:
        print(
            f"    {prod.product_id} {prod.name:<22} "
            f"{prod.category.value:<7} {prod.price_krw:>10,}원"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
