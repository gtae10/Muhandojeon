# -*- coding: utf-8 -*-
"""통합 경로("한 메종" 세계관)용 데이터 3종을 생성한다.

  data/integration_catalog.json    MCM 6종 원본 + 팀 fixture 12종(우리 스키마로 변환)
  data/integration_stores.json     stores.json + stock 보유 매장에 LX 12종 가정값
  data/integration_customers.json  C001~C010 원본 + CU-0001~0006 변환 병합

산출물은 /clienteling/reply 가 knowledge.data_overlay 로 이 파일들을 물릴 때만
쓰인다. /chat(MCM 데모)은 이 파일들을 전혀 읽지 않는다 — 동결 유지.

실행: python scripts/build_integration_data.py
      (팀 브랜치 fixtures 는 origin/AI-clienteling 에서 git show 로 읽는다.
       fixture 가 바뀌면 이 스크립트만 다시 돌리면 된다 — 사본 어긋남 방지)
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TEAM_REF = "origin/AI-clienteling"


def load_team(path):
    """팀 브랜치의 파일을 git show 로 읽는다."""
    raw = subprocess.run(
        ["git", "show", f"{TEAM_REF}:{path}"], capture_output=True, cwd=ROOT
    )
    if raw.returncode != 0:
        sys.exit(f"git show 실패: {path} — 먼저 git fetch origin 을 실행하세요.")
    return json.loads(raw.stdout.decode("utf-8"))


def load_ours(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


# ── 카테고리 세분 번역 ──────────────────────────────────────────
# 예산 분류표의 "고객이 말한 카테고리 안에서만" 필터가 이 어휘로 동작한다.
# Tote 는 MCM 과 어휘("토트")를 공유해야 같은 메종 안에서 교차 상담이 성립한다.
CATEGORY_BY_NAME = (
    ("Top Handle", "탑핸들 백"),
    ("Shoulder", "숄더백"),
    ("Tote", "토트"),
    ("Clutch", "클러치"),
    ("Derby", "구두"),
    ("Oxford", "구두"),
    ("Boot", "부츠"),
    ("Chronograph", "시계"),
    ("Automatic", "시계"),
    ("Long Wallet", "장지갑"),
    ("Card Holder", "카드지갑"),
    ("Belt", "벨트"),
)

# fixture 제품에 MCM 헤리티지가 오귀속되는 것을 막는 데이터 내 지침.
# (프롬프트에 그대로 실린다 — 이 프로젝트의 기존 관행)
HERITAGE_GUARD = (
    "이 제품에는 비세토스·뮌헨 등 특정 라인의 서사를 붙이지 않습니다. "
    "소재와 만듦새의 사실로만 이야기합니다."
)


def convert_product(p):
    """팀 fixture 제품 → 우리 products.json 스키마."""
    name = p["name"]
    category = next((ko for key, ko in CATEGORY_BY_NAME if key in name), "잡화")
    # 사이즈 라벨: stock_by_size 의 키가 곧 전개 사이즈다. 없으면 One Size.
    sizes = list((p.get("stock_by_size") or {}).keys())
    size_label = " / ".join(sizes) if sizes else "One Size"
    item = {
        "product_id": p["product_id"],
        "name_ko": name,           # assets 의 product_name 과 정확히 일치해야 함
        "name_en": name,
        "line": name.split()[0],
        "category": category,
        "size_label": size_label,
        "color": p.get("color", ""),
        "price_krw": p["price_krw"],
        "materials": {"body": p.get("material", "")},
        "note": HERITAGE_GUARD,
    }
    for key in ("collection", "last_code", "care_notes"):
        if p.get(key):
            item[key] = p[key]
    # stock_by_size·image_path 는 넣지 않는다 — 수량이 프롬프트에 실리면
    # 희소성 화법("마지막 한 점")과 매장 표(있음/없음)의 모순을 만든다.
    return item


def assumed_store_stock(p, index, store_ids):
    """LX 제품의 매장별 재고 가정값. 결정적(랜덤 없음)이어야 리허설이 재현된다.

    전사 수량(stock_by_size 합)이 0이면 전 매장 없음.
    아니면 수량만큼의 매장에 '있음' — 시작 매장을 제품마다 돌려 분포를 만든다.
    """
    total = sum(v for v in (p.get("stock_by_size") or {}).values() if isinstance(v, int))
    result = {}
    if total <= 0:
        return {sid: "없음" for sid in store_ids}
    have_count = min(len(store_ids), max(1, total // 2))
    start = index % len(store_ids)
    have = {store_ids[(start + i) % len(store_ids)] for i in range(have_count)}
    for sid in store_ids:
        result[sid] = "있음" if sid in have else "없음"
    return result


def cart_activities(session_scenarios, catalog_names):
    """세션 시나리오의 장바구니 이탈 → recent_activity (고객별 최신 1건).

    add_to_cart 는 고객이 **의도적으로 남긴** 접점이라 언급해도 된다
    ("접점의 두 종류" 원칙). 조회·체류 이벤트는 수동 관측이라 옮기지 않는다.
    이것이 /clienteling/outreach 의 계기가 된다 — 계기가 없으면 먼저 말을
    걸지 않는 것이 정상이다.
    """
    by_customer = {}
    for sc in session_scenarios:
        cid = sc.get("customer_id")
        pid = sc.get("target_product_id")
        name = catalog_names.get(pid)
        if not cid or not name:
            continue
        cart_events = [
            e for e in sc.get("events") or []
            if e.get("event_type") == "add_to_cart"
        ]
        if not cart_events:
            continue
        date = str(cart_events[-1].get("timestamp") or "")[:10]
        activity = {
            "type": "온라인 장바구니 이탈",
            "intentional": True,
            "product_id": pid,
            "product_name": name,
        }
        if date:
            activity["date"] = date
        prev = by_customer.get(cid)
        if not prev or activity.get("date", "") > prev.get("date", ""):
            by_customer[cid] = activity
    return by_customer


def convert_customer(c, assets, catalog_names):
    """팀 fixture 고객 → 우리 customers.json 스키마. 최소 필드만.

    current_location 은 넣지 않는다 — 매장 접점 근거가 없는 고객의 위치를
    단정하지 않는 기존 원칙 그대로. note 등 내부 메모도 옮기지 않는다.
    """
    owned = []
    for a in assets:
        if a.get("customer_id") != c["customer_id"]:
            continue
        pid = a.get("product_id")
        name = catalog_names.get(pid)
        if not name:
            continue
        product = {
            "product_id": pid,
            "name": name,
            "purchased": str(a.get("purchased_at") or "")[:7],
            # 지문 스캔은 고객이 부티크에 맡겨 이뤄진 의도적 접점이다.
            # 케어 접수 기록으로 변환하면 "지난번 점검해드렸던" 오프닝과
            # 케어 대화의 근거가 된다 (컨디션 notes 대신 이력을 근거로).
            # 키는 원본 customers.json 스키마 그대로 "type" — knowledge.py 가
            # latest["type"] 을 직접 인덱싱한다 ("service" 로 썼다가 500).
            "care_history": (
                [{"date": str(a["last_scanned_at"])[:7],
                  "type": "컨디션 점검", "store": "부티크"}]
                if a.get("last_scanned_at")
                else []
            ),
        }
        notes = "; ".join(
            f.get("note", "").strip()
            for f in a.get("findings") or []
            if isinstance(f, dict) and f.get("note")
        )
        if notes:
            # condition_score 는 옮기지 않는다 (진단서 화법의 원인)
            product["condition"] = {"notes": notes}
        owned.append(product)
    converted = {
        "customer_id": c["customer_id"],
        "name": c.get("name", ""),
        "languages": ["ko"],
        "owned_products": owned,
    }
    # 사실 정보는 실어도 안전하고 상담에 유용하다 (size_profile 은 사이즈 상담 근거).
    # persona_binding·note 는 옮기지 않는다 — 점수·데모 대본 문구가 프롬프트에
    # 유출되는 통로다. current_location 도 넣지 않는다 (근거 없는 위치 단정 방지).
    for key in ("tier", "size_profile", "preferred_categories"):
        if c.get(key):
            converted[key] = c[key]
    return converted


# overall 어휘 → 시연용 컨디션 점수. 재고 가정값과 같은 성격 — 확인된 사실이
# 아니라 데모를 위한 가정이다. C 고객은 자산 등록(지문 스캔) 이전에 만든 더미라
# 자산 ID·점수가 없는데, "한 메종" 세계관에서는 등록됐다는 픽션이 자연스럽다.
SCORE_BY_OVERALL = {"excellent": 95, "good": 85, "fair": 71, "needs_care": 55}
MONTHS_BY_OVERALL = {"excellent": 12, "good": 6, "fair": 2, "needs_care": 1}


def synth_assets_for_c(customers):
    """C001~C010 의 보유 제품 → 시연용 자산 목록 (고객별)."""
    result = {}
    for c in customers:
        assets = []
        for i, p in enumerate(c.get("owned_products") or []):
            overall = (p.get("condition") or {}).get("overall", "good")
            asset = {
                # AS-9 로 시작하는 6자리 = 시연용 가정 자산임을 표시 (팀 자산과 충돌 없음)
                "asset_id": f"AS-9{c['customer_id'][1:]:0>3}{i:02d}",
                "customer_id": c["customer_id"],
                "product_id": p.get("product_id"),
                "product_name": p.get("name"),
                "purchased_at": (p.get("purchased") or "") + "-01T00:00:00+09:00"
                if p.get("purchased") else "",
                "condition_score": SCORE_BY_OVERALL.get(overall, 85),
                "next_service_months": MONTHS_BY_OVERALL.get(overall, 6),
                "findings": (
                    [{"part": "", "severity": "", "note": p["condition"]["notes"]}]
                    if (p.get("condition") or {}).get("notes") else []
                ),
                "care_history": p.get("care_history") or [],
            }
            assets.append(asset)
        if assets:
            result[c["customer_id"]] = assets
    return result


def main():
    team_products = load_team("fixtures/products.json")["products"]
    team_customers = load_team("fixtures/customers.json")["customers"]
    team_assets = load_team("fixtures/assets.json")["assets"]
    team_sessions = load_team("fixtures/session_events.json")["scenarios"]
    ours_products = load_ours("products.json")
    ours_stores = load_ours("stores.json")
    ours_customers = load_ours("customers.json")

    # ── 카탈로그 18종 ──
    converted = [convert_product(p) for p in team_products]
    catalog = {
        "_meta": {
            "description": "통합 경로(한 메종 세계관) 카탈로그. MCM 6종 원본 + 팀 fixture 12종 변환.",
            "generated_by": "scripts/build_integration_data.py — 직접 수정 금지, 스크립트를 고칠 것",
            "rule": ours_products["_meta"].get("rule", ""),
        },
        "products": ours_products["products"] + converted,
    }

    # ── 매장 (stock 보유 매장에 LX 가정값) ──
    stores = json.loads(json.dumps(ours_stores))  # deep copy
    stores["_meta"]["generated_by"] = "scripts/build_integration_data.py — 직접 수정 금지"
    stock_store_ids = [s["id"] for s in stores["stores"] if "stock" in s]
    for i, p in enumerate(team_products):
        assumed = assumed_store_stock(p, i, stock_store_ids)
        for s in stores["stores"]:
            if "stock" in s:
                s["stock"][p["product_id"]] = assumed[s["id"]]

    # ── 고객 16명 ──
    catalog_names = {p["product_id"]: p["name_ko"] for p in catalog["products"]}
    activities = cart_activities(team_sessions, catalog_names)
    converted_customers = []
    for c in team_customers:
        converted = convert_customer(c, team_assets, catalog_names)
        activity = activities.get(c["customer_id"])
        if activity:
            converted["recent_activity"] = activity
        converted_customers.append(converted)
    # _meta 는 원본을 통째로 유지한다. 특히 `today` — load_customer 가 이 값으로
    # C001~C010 의 상대 날짜(귀국일 등)를 시프트하므로 빠지면 시나리오가 어긋난다.
    customers_meta = dict(ours_customers["_meta"])
    customers_meta["description"] = "통합 경로 고객. C001~C010 원본 + 팀 CU-0001~0006 변환."
    customers_meta["generated_by"] = "scripts/build_integration_data.py — 직접 수정 금지"
    customers = {
        "_meta": customers_meta,
        "customers": ours_customers["customers"] + converted_customers,
    }
    assert customers_meta.get("today"), "_meta.today 누락 — 날짜 시프트가 죽는다"

    # ── 검증 (조용한 실패 방지 — 여기서 걸리면 산출물을 쓰면 안 된다) ──
    pids = [p["product_id"] for p in catalog["products"]]
    assert len(pids) == len(set(pids)) == 18, f"pid 유일성 실패: {len(pids)}종"
    for p in catalog["products"]:
        for field in ("product_id", "name_ko", "line", "category", "size_label", "price_krw"):
            assert p.get(field) not in (None, ""), f"{p.get('product_id')} 필수 필드 누락: {field}"
    for s in stores["stores"]:
        if "stock" in s:
            missing = [pid for pid in pids if pid not in s["stock"]]
            assert not missing, f"{s['id']} stock 누락: {missing}"
    asset_names = {
        a["product_id"] for a in team_assets if a.get("product_id")
    } - set(catalog_names)
    assert not asset_names, f"assets 가 가리키는 pid 가 카탈로그에 없음: {asset_names}"
    cids = [c["customer_id"] for c in customers["customers"]]
    assert len(cids) == len(set(cids)) == 16, f"고객 수 이상: {len(cids)}명"

    # ── 고객별 자산 목록 (오케스트레이터가 요청에 실어주는 것의 시연판) ──
    # CU 고객은 팀 fixtures/assets.json 그대로 (+ product_name 조인 + care_history),
    # C 고객은 시연용 가정 자산. preview 페이지가 이걸 요청에 실어 보내면
    # 케어 대화에서 인용 → 근거 카드(점수)가 뜬다.
    assets_by_customer = synth_assets_for_c(ours_customers["customers"])
    for a in team_assets:
        cid = a.get("customer_id")
        if not cid:
            continue
        enriched = dict(a)
        enriched["product_name"] = catalog_names.get(a.get("product_id"), "")
        if a.get("last_scanned_at"):
            enriched["care_history"] = [
                {"date": str(a["last_scanned_at"])[:7], "type": "컨디션 점검", "store": "부티크"}
            ]
        assets_by_customer.setdefault(cid, []).append(enriched)
    assets_doc = {
        "_meta": {
            "description": "고객별 자산 목록. CU 는 팀 fixtures 원본, C(AS-9…)는 시연용 가정값.",
            "generated_by": "scripts/build_integration_data.py — 직접 수정 금지",
        },
        "assets_by_customer": assets_by_customer,
    }
    for cid, items in assets_by_customer.items():
        for a in items:
            assert a.get("asset_id") and a.get("product_name"), f"{cid} 자산 필드 누락: {a}"

    (DATA / "integration_assets.json").write_text(
        json.dumps(assets_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "integration_catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "integration_stores.json").write_text(
        json.dumps(stores, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA / "integration_customers.json").write_text(
        json.dumps(customers, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"카탈로그 {len(pids)}종 / 매장 {len(stock_store_ids)}곳 재고 확장 / 고객 {len(cids)}명 — 검증 통과")


if __name__ == "__main__":
    main()
