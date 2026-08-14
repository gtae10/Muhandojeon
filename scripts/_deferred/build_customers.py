"""고객과 소유 자산 구축 — H&M transactions → 고객 30명 + 개체(asset) 레코드.

`transactions_train.csv` 는 3,000만 행이 넘으므로 **전체를 메모리에 올리지 않는다.**
polars lazy scan(`scan_csv`) + 스트리밍 collect 로 두 번만 훑는다.
1회차: customer_id 별 구매 건수 집계 → 3~20건 고객만 남긴다.
2회차: 선정된 30명의 거래만 뽑는다.

원본이 없으면(H&M 은 대회 규칙 수락이 필요해 403 이 흔하다) `synth_fallback.synth_transactions`
가 **같은 컬럼 구성**의 합성 거래를 만들고, 이후 정규화 로직은 완전히 동일하게 흐른다.

    python -m scripts.build_customers
    python -m scripts.build_customers --force        # 기존 customers.json 덮어쓰기
    python -m scripts.build_customers --scan-limit 5000000   # 느린 환경에서 앞부분만 스캔

티어 배분에 대해
    명세의 필터(3~20건)만 쓰면 NEW(1~2건) 티어가 존재할 수 없다. 그래서 **등록 개체 수**로
    티어를 정한다: 구매 이력 중 최근 N건만 개체 지문이 등록된 것으로 본다(등록 프로그램 도입
    이후 구매). N 은 티어 계획(NEW 6명 / ESTABLISHED 14명 / VIP 10명)에 따라 결정적으로 배정한다.
    페르소나 5종이 티어별로 바인딩되어야 하므로 이 보정이 필요하다.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import polars as pl

from app.config import PROCESSED_DIR, get_settings
from app.domain import (
    CARE_THRESHOLD,
    condition_score,
    findings_for,
    next_service_months,
    purchased_at_for_score,
    stable_hash,
)
from contracts.common import CustomerTier, OwnedAsset, Product, ProductCategory
from scripts.common import (
    CATALOG_PATH,
    CUSTOMERS_PATH,
    HM_TRANSACTIONS,
    KST,
    REFERENCE_NOW,
    asset_id,
    banner,
    customer_id,
    decide_source,
    read_json,
    record_provenance,
    write_json,
)
from scripts.synth_fallback import synth_transactions

N_CUSTOMERS = 30
MIN_PURCHASES = 3
MAX_PURCHASES = 20

#: 티어별 (인원, 등록 개체 수 후보). 합계 30명. 페르소나 5종이 모두 바인딩 가능해야 한다.
TIER_PLAN: tuple[tuple[CustomerTier, int, tuple[int, ...]], ...] = (
    (CustomerTier.VIP, 10, (13, 12, 11, 10, 9, 9, 8, 8, 8, 8)),
    (CustomerTier.ESTABLISHED, 14, (7, 7, 6, 6, 5, 5, 5, 4, 4, 4, 3, 3, 3, 3)),
    (CustomerTier.NEW, 6, (2, 2, 2, 1, 1, 1)),
)

OLDEST_YEARS_AGO = 4.0
NEWEST_MONTHS_AGO = 3.0

#: 데모 대본 핵심 대사용 보정 목표: 컨디션 71점 + 핸들 마모 임계 근접(가방).
PINNED_SCORE = 71
PINNED_CATEGORY = ProductCategory.BAG

_SURNAMES = ("김", "이", "박", "정", "최", "강", "조", "윤", "장", "임", "한", "오", "서", "신")
_GIVEN = (
    "서연",
    "지훈",
    "민재",
    "예린",
    "도현",
    "하윤",
    "준우",
    "수아",
    "지완",
    "채원",
    "태민",
    "은우",
    "가온",
    "현서",
    "다경",
)


@dataclass
class Purchase:
    """원본 거래 1건(정규화 전)."""

    raw_customer_id: str
    raw_article_id: str
    t_dat: datetime


def collect_streaming(frame: pl.LazyFrame) -> pl.DataFrame:
    """스트리밍 엔진으로 collect. 3천만 행을 메모리에 올리지 않기 위한 유일한 진입점."""
    return frame.collect(engine="streaming")


def scan_transactions(scan_limit: int | None) -> tuple[pl.LazyFrame, str, dict[str, Any]]:
    """거래 LazyFrame 을 만든다. 원본이 없으면 합성 거래로 대체."""
    decision = decide_source("customers", HM_TRANSACTIONS)
    print(f"  소스: {decision.label} — {decision.reason}")
    if decision.used_external:
        lazy = pl.scan_csv(
            HM_TRANSACTIONS,
            schema_overrides={"customer_id": pl.String, "article_id": pl.String},
        ).select(["t_dat", "customer_id", "article_id"])
        if scan_limit:
            lazy = lazy.head(scan_limit)
            print(f"  스캔 제한: 앞 {scan_limit:,} 행")
        return lazy, decision.label, {"reason": decision.reason, "scan_limit": scan_limit}

    rows = synth_transactions(seed=get_settings().seed)
    lazy = pl.DataFrame(
        [
            {
                "t_dat": str(r["t_dat"]),
                "customer_id": str(r["customer_id"]),
                "article_id": str(r["article_id"]),
            }
            for r in rows
        ]
    ).lazy()
    return lazy, decision.label, {"reason": decision.reason, "synth_rows": len(rows)}


def pick_customers(lazy: pl.LazyFrame) -> tuple[list[str], dict[str, int]]:
    """구매 3~20건 고객 중 30명을 시드 고정 샘플링하고, 구매 건수를 함께 반환한다."""
    counts = collect_streaming(
        lazy.group_by("customer_id")
        .agg(pl.len().alias("n"))
        .filter((pl.col("n") >= MIN_PURCHASES) & (pl.col("n") <= MAX_PURCHASES))
    )
    print(f"  구매 {MIN_PURCHASES}~{MAX_PURCHASES}건 고객: {counts.height:,}명")
    if counts.height == 0:
        raise SystemExit("! 조건을 만족하는 고객이 없다. 원본 데이터를 확인하라.")

    # 스트리밍 group_by 의 행 순서는 보장되지 않는다 → 정렬 후 시드 샘플링해야 재현된다.
    ordered = counts.sort("customer_id")
    pool_size = min(600, ordered.height)
    pool = ordered.sample(n=pool_size, seed=get_settings().seed, shuffle=True)

    # 티어 계획을 채우려면 구매 건수가 많은 고객이 먼저 필요하다(등록 개체 수 ≤ 구매 건수).
    pool = pool.sort(["n", "customer_id"], descending=[True, False])
    chosen = pool.head(N_CUSTOMERS)
    counts_map = {str(r["customer_id"]): int(r["n"]) for r in chosen.to_dicts()}
    return list(counts_map), counts_map


def fetch_purchases(lazy: pl.LazyFrame, raw_ids: list[str]) -> list[Purchase]:
    """선정 고객의 거래만 2회차 스캔으로 가져온다."""
    frame = collect_streaming(lazy.filter(pl.col("customer_id").is_in(raw_ids)))
    out: list[Purchase] = []
    for row in frame.to_dicts():
        raw_date = str(row["t_dat"])[:10]
        try:
            parsed = datetime.strptime(raw_date, "%Y-%m-%d").replace(tzinfo=KST)
        except ValueError:
            continue
        out.append(
            Purchase(
                raw_customer_id=str(row["customer_id"]),
                raw_article_id=str(row["article_id"]),
                t_dat=parsed,
            )
        )
    print(f"  거래 로드: {len(out):,}건 ({len(raw_ids)}명)")
    return out


def rescale_dates(purchases: list[Purchase]) -> dict[str, datetime]:
    """원본 구매 시점을 '가장 오래된 것이 4년 전, 최근이 3개월 전' 이 되도록 선형 스케일링.

    반환: (raw_customer_id, raw_article_id, 원본시각) 키 → 스케일된 시각.
    """
    if not purchases:
        return {}
    oldest = min(p.t_dat for p in purchases)
    newest = max(p.t_dat for p in purchases)
    span_days = max(1.0, (newest - oldest).days)

    target_new = REFERENCE_NOW - timedelta(days=NEWEST_MONTHS_AGO * 30.44)
    target_old = REFERENCE_NOW - timedelta(days=OLDEST_YEARS_AGO * 365.25)
    target_span = (target_new - target_old).days

    mapping: dict[str, datetime] = {}
    for p in purchases:
        ratio = (p.t_dat - oldest).days / span_days
        mapping[purchase_key(p)] = target_old + timedelta(days=ratio * target_span)
    print(
        f"  구매 시점 스케일링: 원본 {oldest.date()}~{newest.date()} → "
        f"{target_old.date()}~{target_new.date()}"
    )
    return mapping


def purchase_key(p: Purchase) -> str:
    return f"{p.raw_customer_id}|{p.raw_article_id}|{p.t_dat.date()}"


def tier_targets() -> list[tuple[CustomerTier, int]]:
    """(티어, 등록 개체 수) 30개를 계획대로 펼친다."""
    out: list[tuple[CustomerTier, int]] = []
    for tier, count, sizes in TIER_PLAN:
        for idx in range(count):
            out.append((tier, sizes[idx % len(sizes)]))
    assert len(out) == N_CUSTOMERS, f"티어 계획 합계가 {len(out)}명 (30 이어야 함)"
    return out


def display_name(raw_customer_id: str) -> str:
    """가상의 한국어 이름(합성). 원본에는 이름 컬럼이 없다."""
    sur = _SURNAMES[stable_hash("sur", raw_customer_id) % len(_SURNAMES)]
    given = _GIVEN[stable_hash("given", raw_customer_id) % len(_GIVEN)]
    return f"{sur}{given}"


def map_product(
    raw_article_id: str, catalog: list[Product], used: set[str], salt: str = ""
) -> Product:
    """원본 article_id 해시로 카탈로그 40개 중 하나에 결정적으로 매핑한다.

    같은 고객이 같은 상품을 중복 보유하지 않도록 충돌 시 다음 인덱스로 회전한다.
    """
    base = stable_hash("article", salt, raw_article_id) % len(catalog)
    for offset in range(len(catalog)):
        product = catalog[(base + offset) % len(catalog)]
        if product.product_id not in used:
            used.add(product.product_id)
            return product
    return catalog[base]  # pragma: no cover - 40개를 다 쓴 경우


def build_asset(
    seq: int,
    cust_id: str,
    product: Product,
    purchased_at: datetime,
) -> OwnedAsset:
    """개체 1건 생성. 컨디션·소견·서비스 시점은 모두 결정적 계산."""
    aid = asset_id(seq)
    score = condition_score(purchased_at, REFERENCE_NOW, product.category, aid)
    scanned: datetime | None = None
    if stable_hash("scan", aid) % 4 != 0:  # 약 75% 는 스캔 이력 보유
        offset_days = stable_hash("scanday", aid) % 240
        scanned = REFERENCE_NOW - timedelta(days=offset_days)
        if scanned < purchased_at:
            scanned = purchased_at + timedelta(days=7)
    return OwnedAsset(
        asset_id=aid,
        customer_id=cust_id,
        product_id=product.product_id,
        product_name=product.name,
        category=product.category,
        purchased_at=purchased_at,
        condition_score=score,
        findings=findings_for(score, product.category),
        next_service_months=next_service_months(score, product.category, aid),
        last_scanned_at=scanned,
    )


def pin_demo_asset(customers: list[dict[str, Any]]) -> dict[str, str] | None:
    """데모 대본용 보정: 최소 1명은 '컨디션 71점, 핸들 마모 임계 근접' 자산을 갖게 한다.

    구매 시점을 목표 점수에서 역산해 옮기고 컨디션을 다시 계산한다. 점수를 직접 써넣지 않는
    이유는, 컨디션 계산이 단일 규칙(경과연수×마모계수)으로 유지되어야 재현·설명이 가능하기 때문이다.
    """
    for cust in customers:
        if cust["tier"] == CustomerTier.NEW.value:
            continue
        for idx, raw in enumerate(cust["assets"]):
            asset = OwnedAsset.model_validate(raw)
            if asset.category is not PINNED_CATEGORY or not (60 <= asset.condition_score <= 88):
                continue
            new_purchased = purchased_at_for_score(
                PINNED_SCORE, REFERENCE_NOW, asset.category, asset.asset_id
            )
            score = condition_score(new_purchased, REFERENCE_NOW, asset.category, asset.asset_id)
            pinned = asset.model_copy(
                update={
                    "purchased_at": new_purchased,
                    "condition_score": score,
                    "findings": findings_for(score, asset.category),
                    "next_service_months": next_service_months(
                        score, asset.category, asset.asset_id
                    ),
                    "last_scanned_at": REFERENCE_NOW - timedelta(days=42),
                }
            )
            cust["assets"][idx] = pinned.model_dump(mode="json")
            # 구매 시점을 옮겼으므로 요약 필드를 다시 계산한다.
            stamps = sorted(str(a["purchased_at"]) for a in cust["assets"])
            cust["first_purchase_at"] = stamps[0]
            cust["last_purchase_at"] = stamps[-1]
            return {
                "customer_id": str(cust["customer_id"]),
                "asset_id": pinned.asset_id,
                "product_name": pinned.product_name,
                "condition_score": str(pinned.condition_score),
                "next_service_months": str(pinned.next_service_months),
                "headline": pinned.findings[0].note if pinned.findings else "",
            }
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="고객 30명 + 소유 자산 구축")
    ap.add_argument("--force", action="store_true", help="기존 customers.json 을 덮어쓴다")
    ap.add_argument("--scan-limit", type=int, default=None, help="원본 앞부분만 스캔(행 수)")
    args = ap.parse_args()

    banner("고객·소유자산 구축")
    if CUSTOMERS_PATH.exists() and not args.force:
        print(f"  이미 존재: {CUSTOMERS_PATH.name} → 재생성하려면 --force")
        return 0
    if not CATALOG_PATH.exists():
        print("  ! 카탈로그가 없다. 먼저 `python -m scripts.build_catalog` 를 실행하라.")
        return 1

    catalog = [Product.model_validate(item) for item in read_json(CATALOG_PATH)["items"]]
    lazy, source_label, meta = scan_transactions(args.scan_limit)
    raw_ids, purchase_counts = pick_customers(lazy)
    purchases = fetch_purchases(lazy, raw_ids)
    scaled = rescale_dates(purchases)

    by_customer: dict[str, list[Purchase]] = {}
    for p in purchases:
        by_customer.setdefault(p.raw_customer_id, []).append(p)

    # 구매 건수 내림차순으로 티어 계획을 배정한다(등록 개체 수 ≤ 구매 건수 보장).
    ordered_raw = sorted(raw_ids, key=lambda rid: (-purchase_counts[rid], rid))
    plan = tier_targets()

    customers: list[dict[str, Any]] = []
    seq = 1
    for idx, raw_id in enumerate(ordered_raw):
        tier, target_assets = plan[idx]
        cust_id = customer_id(idx + 1)
        history = sorted(by_customer.get(raw_id, []), key=lambda p: scaled[purchase_key(p)])
        registered = history[-min(target_assets, len(history)) :]

        used_products: set[str] = set()
        assets: list[OwnedAsset] = []
        for p in registered:
            product = map_product(p.raw_article_id, catalog, used_products, salt=cust_id)
            assets.append(build_asset(seq, cust_id, product, scaled[purchase_key(p)]))
            seq += 1

        actual_tier = tier_for(len(assets))
        customers.append(
            {
                "customer_id": cust_id,
                "display_name": display_name(raw_id),
                "tier": actual_tier.value,
                "planned_tier": tier.value,
                "purchase_count": purchase_counts[raw_id],
                "asset_count": len(assets),
                "first_purchase_at": assets[0].purchased_at.isoformat() if assets else None,
                "last_purchase_at": assets[-1].purchased_at.isoformat() if assets else None,
                "source": {
                    "dataset": "h-and-m-personalized-fashion-recommendations"
                    if source_label == "external"
                    else "synth",
                    "raw_customer_id_sha": stable_hash("cid", raw_id),
                },
                "assets": [a.model_dump(mode="json") for a in assets],
            }
        )

    pinned = pin_demo_asset(customers)
    if pinned:
        print(
            f"  데모 보정: {pinned['customer_id']} / {pinned['asset_id']} "
            f"({pinned['product_name']}) → 컨디션 {pinned['condition_score']}점, "
            f"케어 {pinned['next_service_months']}개월 후 / {pinned['headline']}"
        )
    else:
        print("  ! 데모 보정 실패 — 컨디션 71점 가방 자산을 만들 후보가 없다")

    total_assets = sum(len(c["assets"]) for c in customers)
    tier_counts: dict[str, int] = {}
    for c in customers:
        tier_counts[c["tier"]] = tier_counts.get(c["tier"], 0) + 1
    scores = [a["condition_score"] for c in customers for a in c["assets"]]
    care_now = sum(1 for s in scores if s <= CARE_THRESHOLD)

    payload = {
        "generated_with": {
            "source": source_label,
            "reference_now": REFERENCE_NOW.isoformat(),
            "seed": get_settings().seed,
            "tier_plan": {t.value: n for t, n, _ in TIER_PLAN},
            "pinned_demo_asset": pinned,
        },
        "customers": customers,
    }
    write_json(CUSTOMERS_PATH, payload)
    record_provenance(
        "customers",
        {
            **meta,
            "source": source_label,
            "customers": len(customers),
            "assets": total_assets,
            "tier_counts": tier_counts,
            "condition_min": min(scores) if scores else None,
            "condition_max": max(scores) if scores else None,
            "care_due_now": care_now,
            "pinned_demo_asset": pinned,
        },
    )
    print(f"  저장: {CUSTOMERS_PATH.relative_to(PROCESSED_DIR.parent.parent)}")
    print(f"  고객 {len(customers)}명 / 개체 {total_assets}개 / 티어 {tier_counts}")
    print(f"  컨디션 {min(scores)}~{max(scores)}점, 케어 임계({CARE_THRESHOLD}) 이하 {care_now}개")
    return 0


def tier_for(asset_count: int) -> CustomerTier:
    """등록 개체 수 기준 티어. NEW 1~2 / ESTABLISHED 3~7 / VIP 8 이상."""
    if asset_count >= 8:
        return CustomerTier.VIP
    if asset_count >= 3:
        return CustomerTier.ESTABLISHED
    return CustomerTier.NEW


if __name__ == "__main__":
    sys.exit(main())
