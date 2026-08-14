# -*- coding: utf-8 -*-
import sys, io
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
"""
etl/remap_data.py - 럭셔리 브랜드 데이터 리매핑 ETL 스크립트
H&M Dataset + Fashion Product Images + Coveo 기반 시뮬레이션
실행: python etl/remap_data.py
"""

import uuid
import random
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

random.seed(42)
np.random.seed(42)

OUTPUT_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)


# ════════════════════════════════════════════════════════
# 1. 럭셔리 상품 카탈로그 (H&M Article 리매핑)
# ════════════════════════════════════════════════════════

LUXURY_CATALOG = [
    # (brand, name, category, sub_category, material, price_usd, launch_year)
    ("Louis Vuitton", "Neverfull MM",        "Bag",    "Tote",      "Monogram Canvas / Cowhide",  1650,  2007),
    ("Louis Vuitton", "Speedy 30",           "Bag",    "Handbag",   "Damier Ebene Canvas",        1200,  1930),
    ("Louis Vuitton", "Pochette Métis",      "Bag",    "Shoulder",  "Monogram Empreinte Leather", 2100,  2015),
    ("Chanel",        "Classic Flap Medium", "Bag",    "Flap",      "Lambskin / Gold HW",         9500,  1955),
    ("Chanel",        "Coco Handle",         "Bag",    "Top Handle","Grained Calfskin",           6800,  2014),
    ("Hermès",        "Birkin 30",           "Bag",    "Tote",      "Togo Leather / Palladium",  11800,  1984),
    ("Hermès",        "Kelly 25",            "Bag",    "Structured","Epsom Leather / Gold HW",   10500,  1935),
    ("Gucci",         "GG Marmont Medium",   "Bag",    "Shoulder",  "Matelassé Chevron Leather",  2350,  2016),
    ("Dior",          "Lady Dior Medium",    "Bag",    "Structured","Cannage Lambskin",           5500,  1994),
    ("Bottega Veneta","Jodie Medium",        "Bag",    "Hobo",      "Intrecciato Nappa",          4100,  2020),
    # Wallet
    ("Louis Vuitton", "Zippy Wallet",        "Wallet", "Long",      "Monogram Canvas",             745,  2000),
    ("Chanel",        "Classic Long Wallet", "Wallet", "Long",      "Caviar Leather",             1850,  2010),
    ("Hermès",        "Bearn Wallet",        "Wallet", "Long",      "Epsom Leather",              1950,  2005),
    ("Gucci",         "GG Supreme Wallet",   "Wallet", "Bifold",    "GG Supreme Canvas",           445,  2017),
    ("Dior",          "Saddle Compact Wallet","Wallet","Compact",   "Oblique Jacquard",            650,  2018),
    # Watch
    ("Rolex",         "Datejust 36",         "Watch",  "Dress",     "Oystersteel / Rolesor",     10000,  1945),
    ("Rolex",         "Submariner Date",     "Watch",  "Dive",      "Oystersteel / Cerachrom",   12000,  1953),
    ("Patek Philippe","Calatrava 5227",      "Watch",  "Dress",     "Rose Gold / Alligator",     45000,  2012),
    ("Audemars Piguet","Royal Oak 15500ST",  "Watch",  "Sport",     "Stainless Steel / Tapisserie",34000, 1972),
    ("Cartier",       "Tank Must",           "Watch",  "Dress",     "Steel / Vegan Leather",      3500,  2021),
]


def build_product_catalog() -> pd.DataFrame:
    records = []
    for brand, name, cat, sub_cat, material, price, year in LUXURY_CATALOG:
        records.append({
            "product_id":   str(uuid.uuid4()),
            "name":         name,
            "brand":        brand,
            "category":     cat,
            "sub_category": sub_cat,
            "material":     material,
            "color":        random.choice(["Black", "Beige", "Brown", "Navy", "Gold", "Silver", "Burgundy"]),
            "price_usd":    price,
            "launch_year":  year,
            "sku":          f"{brand[:3].upper()}-{name[:4].upper().replace(' ','')}-{year}",
            "description":  f"Iconic {brand} {name} crafted from {material}.",
            "extra_meta":   json.dumps({"limited_edition": random.random() < 0.15, "season": "All-Season"}),
        })
    return pd.DataFrame(records)


# ════════════════════════════════════════════════════════
# 2. 고객 100명 샘플링 (H&M Customer 리매핑)
# ════════════════════════════════════════════════════════

FIRST_NAMES = ["Jihyun","Soyeon","Minji","Areum","Jiwoo","Hana","Yuna","Seoyeon",
               "Emily","Sophia","Isabella","Olivia","Charlotte","Ava","Mia",
               "Yuki","Hana","Mei","Sakura","Rin","Wei","Xin","Lei","Fang",
               "Elena","Sofia","Valentina","Camille","Amélie","Chiara"]
LAST_NAMES  = ["Kim","Lee","Park","Choi","Jung","Kang","Yoon","Lim",
               "Smith","Johnson","Williams","Brown","Jones","Garcia",
               "Yamamoto","Tanaka","Suzuki","Watanabe",
               "Wang","Zhang","Liu","Chen",
               "Müller","Schneider","Fischer","Dupont"]
TIERS       = ["Bronze", "Silver", "Gold", "Platinum"]
TIER_WEIGHTS= [0.25, 0.40, 0.25, 0.10]
COUNTRIES   = ["KR","US","JP","CN","FR","DE","IT","GB","SG","AE"]


def build_users(n: int = 100) -> pd.DataFrame:
    records = []
    for _ in range(n):
        name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
        uid  = str(uuid.uuid4())
        records.append({
            "user_id":    uid,
            "name":       name,
            "email":      f"{uid[:8]}@luxury-clienteling.com",
            "tier":       random.choices(TIERS, weights=TIER_WEIGHTS)[0],
            "country":    random.choice(COUNTRIES),
            "created_at": (datetime.now() - timedelta(days=random.randint(30, 1800))).isoformat(),
            "is_active":  True,
        })
    return pd.DataFrame(records)


# ════════════════════════════════════════════════════════
# 3. 자산 + 컨디션 데이터 (핵심)
# ════════════════════════════════════════════════════════

def score_to_grade(score: int) -> str:
    if score >= 90: return "Mint"
    if score >= 75: return "Excellent"
    if score >= 55: return "Good"
    if score >= 30: return "Fair"
    return "Poor"


def generate_wear_details(score: int) -> dict:
    """컨디션 점수 기반 마모 세부 정보 생성"""
    severity = max(0, (100 - score) / 100)
    return {
        "scratches":       int(np.random.poisson(severity * 8)),
        "cracks":          int(np.random.poisson(severity * 2)),
        "color_fade":      severity > 0.35 and random.random() < severity,
        "hardware_tarnish":severity > 0.25 and random.random() < severity * 0.7,
        "lining_damage":   severity > 0.45 and random.random() < severity * 0.5,
        "strap_wear":      severity > 0.30 and random.random() < severity * 0.6,
    }


def build_assets(users: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    records = []
    product_list = products.to_dict("records")

    for _, user in users.iterrows():
        # 고객 등급에 따라 보유 자산 수 조정
        tier_asset_count = {
            "Bronze": (1, 2), "Silver": (2, 4),
            "Gold":   (3, 6), "Platinum": (5, 10)
        }
        lo, hi = tier_asset_count[user["tier"]]
        n_assets = random.randint(lo, hi)
        owned_products = random.sample(product_list, min(n_assets, len(product_list)))

        for prod in owned_products:
            # 구매일: 최소 30일 전 ~ 최대 5년 전
            purchase_date = datetime.now() - timedelta(days=random.randint(30, 1825))
            # 오래될수록 컨디션이 낮을 가능성 높음
            age_days = (datetime.now() - purchase_date).days
            base_score = max(10, 100 - int(age_days * random.uniform(0.01, 0.05)))
            condition_score = int(np.clip(np.random.normal(base_score, 10), 1, 100))

            records.append({
                "asset_id":         str(uuid.uuid4()),
                "user_id":          user["user_id"],
                "product_id":       prod["product_id"],
                "purchase_date":    purchase_date.isoformat(),
                "purchase_price":   round(prod["price_usd"] * random.uniform(0.85, 1.05), 2),
                "purchase_channel": random.choice(["flagship_store", "online", "resale"]),
                "condition_score":  condition_score,
                "condition_grade":  score_to_grade(condition_score),
                "wear_details":     json.dumps(generate_wear_details(condition_score)),
                "last_assessed":    (datetime.now() - timedelta(days=random.randint(0, 90))).isoformat(),
                "notes":            None,
            })

    return pd.DataFrame(records)


# ════════════════════════════════════════════════════════
# 4. 세션 이벤트 (Coveo 기반 망설임 시뮬레이션)
# ════════════════════════════════════════════════════════

EVENT_PATTERNS = {
    "high_hesitation":   ["view","view","view","add_to_cart","remove_from_cart","view","abandon"],
    "medium_hesitation": ["view","view","add_to_cart","abandon"],
    "low_hesitation":    ["view","add_to_cart","purchase"],
    "browsing_only":     ["view","view","view","abandon"],
}


def build_session_events(users: pd.DataFrame, products: pd.DataFrame, n_sessions: int = 300) -> pd.DataFrame:
    records       = []
    product_ids   = products["product_id"].tolist()
    user_ids      = users["user_id"].tolist()
    pattern_names = list(EVENT_PATTERNS.keys())
    pattern_weights = [0.30, 0.30, 0.25, 0.15]

    for _ in range(n_sessions):
        user_id    = random.choice(user_ids)
        session_id = str(uuid.uuid4())
        product_id = random.choice(product_ids)
        pattern    = random.choices(pattern_names, weights=pattern_weights)[0]
        event_seq  = EVENT_PATTERNS[pattern]

        base_time  = datetime.now() - timedelta(days=random.randint(0, 60))

        for i, etype in enumerate(event_seq):
            event_time = base_time + timedelta(seconds=i * random.randint(30, 300))
            records.append({
                "event_id":    str(uuid.uuid4()),
                "user_id":     user_id,
                "session_id":  session_id,
                "product_id":  product_id if etype != "abandon" else None,
                "event_type":  etype,
                "event_at":    event_time.isoformat(),
                "duration_sec":round(random.uniform(5, 240), 2),
                "device":      random.choice(["mobile", "desktop", "tablet"]),
                "referrer":    random.choice(["direct","instagram","kakao","google","email"]),
                "extra_data":  json.dumps({"hesitation_pattern": pattern}),
            })

    return pd.DataFrame(records)


# ════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════

def main():
    print("[1/4] 럭셔리 상품 카탈로그 생성 중...")
    products = build_product_catalog()
    products.to_csv(OUTPUT_DIR / "products.csv", index=False, encoding="utf-8-sig")
    print(f"  OK {len(products)}개 상품 저장 -> data/products.csv")

    print("[2/4] 고객 100명 샘플링 중...")
    users = build_users(100)
    users.to_csv(OUTPUT_DIR / "users.csv", index=False, encoding="utf-8-sig")
    print(f"  OK {len(users)}명 저장 -> data/users.csv")

    print("[3/4] 자산 + 컨디션 데이터 생성 중...")
    assets = build_assets(users, products)
    assets.to_csv(OUTPUT_DIR / "assets.csv", index=False, encoding="utf-8-sig")
    print(f"  OK {len(assets)}개 자산 저장 -> data/assets.csv")

    print("[4/4] 세션 이벤트(망설임) 시뮬레이션 중...")
    events = build_session_events(users, products, n_sessions=300)
    events.to_csv(OUTPUT_DIR / "session_events.csv", index=False, encoding="utf-8-sig")
    print(f"  OK {len(events)}개 이벤트 저장 -> data/session_events.csv")

    print("\n[ETL 완료] data/ 디렉터리를 확인하세요.")
    print(f"  - products.csv      : {len(products)}행")
    print(f"  - users.csv         : {len(users)}행")
    print(f"  - assets.csv        : {len(assets)}행")
    print(f"  - session_events.csv: {len(events)}행")


if __name__ == "__main__":
    main()
