"""데이터 출처 문서 생성기 — `docs/DATA_PROVENANCE.md`.

필드별 출처 판정(정적 표)은 이 파일에 있고, 최근 빌드 결과(동적)는
`data/processed/provenance.json` 에서 읽어 붙인다. 그래서 문서가 실제 빌드와 어긋나지 않는다.

    python -m scripts.gen_provenance_doc
"""

from __future__ import annotations

import json
import sys
from typing import Any

from app.config import DOCS_DIR, ROOT
from scripts.common import PROVENANCE_PATH, read_json

Origin = str
ORIGIN_RAW: Origin = "원본"
ORIGIN_DERIVED: Origin = "원본 파생"
ORIGIN_RULE: Origin = "합성(규칙)"
ORIGIN_WRITTEN: Origin = "창작(LLM/템플릿)"

#: 엔티티별 (필드, 출처, 설명). 이 표가 "어디까지 진짜냐"에 대한 답이다.
FIELD_ORIGINS: dict[str, list[tuple[str, Origin, str]]] = {
    "상품 (catalog_luxury.json / products)": [
        ("product_id", ORIGIN_RULE, "우리 id 부여 (LX-0001~LX-0040)"),
        ("category", ORIGIN_DERIVED, "styles.csv 의 subCategory/articleType 매핑"),
        ("name", ORIGIN_WRITTEN, "럭셔리 톤 리라이팅. 원본명은 source.raw_display_name 에 보존"),
        ("collection", ORIGIN_WRITTEN, "가상의 컬렉션명 (실존 브랜드 미사용)"),
        ("material", ORIGIN_WRITTEN, "카테고리별 소재/제법 어휘에서 결정적 선택"),
        ("color", ORIGIN_DERIVED, "원본 baseColour → 럭셔리 컬러명 매핑 (Black→Noir 등)"),
        ("price_krw", ORIGIN_RULE, "카테고리 가격대 안에서 해시 기반 결정적 선택 (150만~1,200만)"),
        (
            "size_system / available_sizes",
            ORIGIN_RULE,
            "카테고리별 사이즈 체계. 재고는 해시로 축소",
        ),
        ("care_notes", ORIGIN_WRITTEN, "카테고리별 케어 가이드 문구"),
        (
            "image_path",
            ORIGIN_RAW,
            "Fashion Product Images 원본 이미지 사본 (60x80, 리사이즈 없음)",
        ),
        ("source.*", ORIGIN_RAW, "원본 id·articleType·baseColour·연도·원본 상품명"),
    ],
    "고객 (customers.json / customers)": [
        ("customer_id", ORIGIN_RULE, "우리 id 부여 (CU-0001~CU-0030)"),
        ("purchase_count", ORIGIN_RAW, "H&M 거래 건수 (3~20건 필터 통과)"),
        ("tier", ORIGIN_DERIVED, "등록 개체 수 기준 (NEW 1~2 / ESTABLISHED 3~7 / VIP 8+)"),
        ("display_name", ORIGIN_RULE, "**전량 합성.** 원본에 이름 컬럼이 없다"),
        ("first/last_purchase_at", ORIGIN_DERIVED, "원본 구매 시점을 상대 시점으로 스케일링"),
        ("source.raw_customer_id_sha", ORIGIN_DERIVED, "원본 customer_id 의 해시(원문 미저장)"),
    ],
    "소유 개체 (assets)": [
        ("asset_id", ORIGIN_RULE, "우리 id 부여 (AS-000001~)"),
        ("product_id", ORIGIN_DERIVED, "원본 article_id 해시 → 카탈로그 40개 중 결정적 매핑"),
        (
            "purchased_at",
            ORIGIN_DERIVED,
            "원본 t_dat 을 '가장 오래된 것이 4년 전, 최근이 3개월 전' 으로 선형 스케일링",
        ),
        (
            "condition_score",
            ORIGIN_RULE,
            "100 - 경과연수 × 카테고리 마모계수 × 사용강도. 난수 없음(해시 기반 결정적)",
        ),
        ("findings", ORIGIN_RULE, "점수 구간 × 카테고리별 부위 순서로 생성한 소견 문장"),
        ("next_service_months", ORIGIN_RULE, "컨디션 70 도달까지 남은 개월 수 계산값"),
        (
            "last_scanned_at",
            ORIGIN_RULE,
            "약 75% 개체에 스캔 이력 부여(해시). 실제 스캔은 등록 CLI 가 갱신",
        ),
    ],
    "세션 (sessions.json / sessions)": [
        (
            "session 단위",
            ORIGIN_RAW,
            "**(UserID, SessionID) 조합.** SessionID 단독은 1~10 버킷일 뿐",
        ),
        ("abandoned", ORIGIN_RAW, "add_to_cart 있고 purchase 없음"),
        (
            "events[].event_type",
            "혼합",
            "page_view/product_view/click/add_to_cart/purchase 는 원본 파생. "
            "size_guide/price_filter_change/stock_check/shipping_info/back_to_category/image_zoom 는 합성",
        ),
        (
            "events[].timestamp",
            ORIGIN_RULE,
            "**전량 합성.** 원본은 한 세션의 시각이 수개월에 흩어져 있어 시간축으로 쓸 수 없다(순서만 사용)",
        ),
        ("events[].dwell_seconds", ORIGIN_RULE, "**전량 합성.** 원본에 체류시간 컬럼이 없다"),
        ("events[].meta.synthetic", ORIGIN_RULE, "이 이벤트가 합성인지 여부를 이벤트마다 표시"),
        ("customer_id / target_product_id", ORIGIN_DERIVED, "원본 UserID / ProductID 해시 매핑"),
        (
            "hesitation_label",
            ORIGIN_RULE,
            "최종 이벤트 시퀀스에 `app.intent_rules.classify` 규칙을 적용해 도출",
        ),
    ],
}

LIMITATIONS = """## 한계 (먼저 밝힌다)

1. **망설임 라벨은 사람이 붙인 것이 아니다.** 규칙 엔진(`app/intent_rules.py`)이 이벤트
   시퀀스에서 도출한다. 그리고 그 판별 이벤트 자체가 원본 통계에서 파생 합성된 것이므로,
   AI1 학습셋의 상한은 "규칙 재현"이다. 규칙을 외운 모델의 val 정확도 1.0 은 성능이 아니라
   누수다. 이 점을 `exports/README.md` 에도 적어 두었다.
   - 완화책: 프로파일 결정에 **원본에서 살아남은 특성만** 쓴다(상품 다양성, 장바구니 이후 탐색
     횟수, 클릭 수, 고객 보유 자산 평균가 대비 대상 가격). 목표 라벨을 먼저 정하고 근거를
     만드는 방식은 쓰지 않았다.
2. **원본 클릭스트림의 이벤트 어휘가 7종뿐**이다(page_view, product_view, click, add_to_cart,
   purchase, login, logout). 사이즈·가격·재고 관련 판별 이벤트는 존재하지 않아 합성이 불가피했다.
3. **원본 세션의 타임스탬프는 세션 시간축으로 쓸 수 없다.** 한 (UserID, SessionID) 안에서
   시각이 수개월에 걸쳐 흩어져 있다. 순서만 살리고 시각/체류시간은 규칙 합성했다.
4. **동일 상품 반복 조회 신호가 원본에 없다.** 모든 세션의 `repeat_max` 가 1이라 사이즈 고민의
   직접 증거로 쓸 수 없었고, 대신 "사이즈 체계가 있는 카테고리 + 소수 상품 집중"으로 대체했다.
5. **상품 이미지가 60x80** 이다(Fashion Product Images "Small" 버전). 인위적 업스케일은 오히려
   흐려 보여서 원본 해상도를 유지하고 `source.image_px` 에 실제 크기를 기록했다. 발표 화면에서는
   작게 렌더하는 편이 낫다.
6. **컨디션 점수는 시간 기반 추정치**다. 실제 이미지 기반 컨디션 판정은 백엔드 담당의
   `POST /condition/score` 실구현 몫이며, 목 어댑터는 이 추정치를 그대로 반환한다.
7. **H&M 거래가 없으면 합성 거래로 대체**된다(대회 규칙 미동의 시 403). 어느 슬라이스가 합성인지는
   아래 '최근 빌드 결과' 에 그대로 나온다.
"""

POLICY = """## 재현성 정책

| 항목 | 값 | 이유 |
|---|---|---|
| 시드 | `seed=42` (모든 샘플링·분할) | 데모가 매번 달라지면 발표 대본이 깨진다 |
| 기준시각 | `REFERENCE_NOW = 2026-08-14T12:00:00+09:00` 고정 | 컨디션 점수가 경과 연수 함수라 `now()` 를 쓰면 매일 점수가 흔들린다 |
| 난수 | 사용하지 않음. 모든 "무작위성"은 `sha1(문자열)` 기반 결정적 선택 | 플랫폼·실행 간 동일 결과 보장 (파이썬 `hash()` 는 문자열에 대해 실행마다 달라져서 쓰지 않는다) |
| 카탈로그 | `catalog_luxury.json` 은 `--force` 없이 재생성 금지 | 상품명이 바뀌면 발표 대본이 깨진다 |

`REFERENCE_NOW` 를 바꾸려면 env 로만: `REFERENCE_NOW=2026-09-01T12:00:00+09:00 make data`
(컨디션 점수와 '컨디션 71점' 보정이 함께 이동한다).
"""


def build_dynamic() -> str:
    """최근 빌드 결과 섹션."""
    if not PROVENANCE_PATH.exists():
        return (
            "## 최근 빌드 결과\n\n"
            "`data/processed/provenance.json` 이 없다. `make data` 를 먼저 실행하라.\n"
        )
    data: dict[str, Any] = read_json(PROVENANCE_PATH)
    lines = [
        "## 최근 빌드 결과",
        "",
        "빌드마다 자동 기록된다(`data/processed/provenance.json`).",
        "",
    ]
    for step, payload in data.items():
        lines.append(f"### `{step}`")
        lines.append("")
        lines.append("| 항목 | 값 |")
        lines.append("|---|---|")
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                rendered = f"`{json.dumps(value, ensure_ascii=False)}`"
                if len(rendered) > 300:
                    rendered = rendered[:297] + "…`"
            else:
                rendered = f"`{value}`"
            lines.append(f"| {key} | {rendered} |")
        lines.append("")
    return "\n".join(lines)


def build_static() -> str:
    lines = ["## 필드별 출처", "", "판정 기준: "]
    lines.append(
        f"**{ORIGIN_RAW}** = 원본 값 그대로 / "
        f"**{ORIGIN_DERIVED}** = 원본 값을 변환·매핑 / "
        f"**{ORIGIN_RULE}** = 원본에 없어 규칙으로 생성 / "
        f"**{ORIGIN_WRITTEN}** = 문구를 창작(LLM 또는 결정적 템플릿)"
    )
    lines.append("")
    for entity, fields in FIELD_ORIGINS.items():
        lines.append(f"### {entity}")
        lines.append("")
        lines.append("| 필드 | 출처 | 설명 |")
        lines.append("|---|---|---|")
        for field, origin, detail in fields:
            lines.append(f"| `{field}` | {origin} | {detail} |")
        lines.append("")
    return "\n".join(lines)


HEADER = """# 데이터 출처 (Provenance)

> 이 문서는 **자동 생성**된다. 필드별 판정은 `scripts/gen_provenance_doc.py` 에, 빌드 결과는
> `data/processed/provenance.json` 에 있다. 재생성: `python -m scripts.gen_provenance_doc`

심사위원 질문 대응용 문서다. **"이 데이터 진짜냐"** 에 대한 답은 한 문장으로:
행동 골격과 구매 이력은 공개 데이터셋에서 왔고, 럭셔리 서사(제품명·가격)와 컨디션 점수·판별
이벤트는 규칙으로 생성했다. 어느 필드가 어디서 왔는지는 아래 표에 전부 적어 두었다.

라이선스는 `docs/DATA_LICENSES.md`, 계약은 `docs/CONTRACTS.md` 참고.
"""


def main() -> int:
    doc = "\n".join([HEADER, POLICY, build_static(), LIMITATIONS, build_dynamic()])
    path = DOCS_DIR / "DATA_PROVENANCE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
    print(f"문서 생성: {path.relative_to(ROOT)} ({len(doc.splitlines())} 줄)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
