"""도메인 규칙 — 컨디션 계산, 부위별 소견, 럭셔리 어휘, 카테고리 매핑.

데이터 빌더(`scripts/build_*.py`, `scripts/synth_fallback.py`)와 목 어댑터가 같은 규칙을
쓰도록 여기 모았다. **모든 계산은 결정적**이다(난수 없음). 같은 입력 → 항상 같은 출력.

컨디션 점수 모델
    score = clamp(100 - 경과연수 × 카테고리_마모계수 × 사용강도, 20, 100)

    - 카테고리_마모계수: 연 4~14점. 신발(14)이 가방(7.5)보다 빠르게 떨어진다.
    - 사용강도: asset_id 해시로 {0.85, 1.0, 1.15} 중 하나. 결정적이지만 자연스러운 분산을 준다.
    - 70점이 케어 권장 임계값이다. `next_service_months` 는 70 도달까지 남은 개월 수.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from contracts.common import AssetPart, Finding, ProductCategory, Severity

CARE_THRESHOLD = 70
"""컨디션 케어 권장 임계값. 이 값 이하면 즉시 케어를 제안한다."""

WEAR_RATE_PER_YEAR: dict[ProductCategory, float] = {
    ProductCategory.SHOES: 14.0,
    ProductCategory.WALLET: 9.0,
    ProductCategory.BELT: 8.0,
    ProductCategory.OUTERWEAR: 7.8,
    ProductCategory.BAG: 7.5,
    ProductCategory.ACCESSORY: 6.5,
    ProductCategory.WATCH: 4.0,
}
"""연간 컨디션 감소폭. 명세의 '연 6~14점, 가방보다 신발이 빠르게' 를 반영."""

USAGE_FACTORS: tuple[float, ...] = (0.85, 1.0, 1.15)
"""사용 강도. asset_id 해시로 고른다(결정적)."""

#: 카테고리별 마모가 먼저 나타나는 부위 순서. findings 생성과 촬영 부위 규약이 이 순서를 쓴다.
CATEGORY_PARTS: dict[ProductCategory, tuple[AssetPart, ...]] = {
    ProductCategory.BAG: (
        AssetPart.HANDLE,
        AssetPart.CORNER,
        AssetPart.HARDWARE,
        AssetPart.STITCHING,
        AssetPart.LINING,
    ),
    ProductCategory.SHOES: (
        AssetPart.SOLE,
        AssetPart.UPPER,
        AssetPart.EDGE_COAT,
        AssetPart.STITCHING,
        AssetPart.LINING,
    ),
    ProductCategory.WATCH: (AssetPart.BRACELET, AssetPart.DIAL, AssetPart.HARDWARE),
    ProductCategory.BELT: (AssetPart.EDGE_COAT, AssetPart.HARDWARE, AssetPart.EXTERIOR),
    ProductCategory.WALLET: (
        AssetPart.EDGE_COAT,
        AssetPart.STITCHING,
        AssetPart.LINING,
        AssetPart.HARDWARE,
    ),
    ProductCategory.OUTERWEAR: (AssetPart.EXTERIOR, AssetPart.LINING, AssetPart.STITCHING),
    ProductCategory.ACCESSORY: (AssetPart.EXTERIOR, AssetPart.HARDWARE, AssetPart.STITCHING),
}

#: (부위, 심각도) → 소견 문장. 상담 문구가 이 문장을 인용한다.
FINDING_NOTES: dict[tuple[AssetPart, Severity], str] = {
    (AssetPart.HANDLE, Severity.LOW): "핸들 표면 광택 변화 경미",
    (AssetPart.HANDLE, Severity.MEDIUM): "핸들 마모 진행, 재코팅 권장 시점 근접",
    (AssetPart.HANDLE, Severity.HIGH): "핸들 코팅 박리 및 심재 노출",
    (AssetPart.CORNER, Severity.LOW): "코너 마찰 흔적 경미",
    (AssetPart.CORNER, Severity.MEDIUM): "코너 4곳 마찰, 각 세우기 필요",
    (AssetPart.CORNER, Severity.HIGH): "코너 가죽 마모로 심재 노출",
    (AssetPart.HARDWARE, Severity.LOW): "금속 광택 양호, 미세 스크래치",
    (AssetPart.HARDWARE, Severity.MEDIUM): "금속 변색 시작(도금 산화)",
    (AssetPart.HARDWARE, Severity.HIGH): "도금 박리, 재도금 필요",
    (AssetPart.STITCHING, Severity.LOW): "스티치 텐션 양호",
    (AssetPart.STITCHING, Severity.MEDIUM): "접합부 스티치 이완",
    (AssetPart.STITCHING, Severity.HIGH): "스티치 절단 구간 발생",
    (AssetPart.LINING, Severity.LOW): "내부 라이닝 청결",
    (AssetPart.LINING, Severity.MEDIUM): "라이닝 얼룩 및 늘어짐",
    (AssetPart.LINING, Severity.HIGH): "라이닝 찢어짐",
    (AssetPart.SOLE, Severity.LOW): "아웃솔 트레드 양호",
    (AssetPart.SOLE, Severity.MEDIUM): "앞창 마모 진행, 재밑창 시점 근접",
    (AssetPart.SOLE, Severity.HIGH): "앞창 관통 마모, 재밑창 필요",
    (AssetPart.UPPER, Severity.LOW): "볼 부분 주름 자연 발생",
    (AssetPart.UPPER, Severity.MEDIUM): "갑피 주름 심화, 보습 필요",
    (AssetPart.UPPER, Severity.HIGH): "갑피 크랙 발생",
    (AssetPart.EDGE_COAT, Severity.LOW): "엣지 코트 상태 양호",
    (AssetPart.EDGE_COAT, Severity.MEDIUM): "엣지 코트 벗겨짐 구간 확인",
    (AssetPart.EDGE_COAT, Severity.HIGH): "엣지 코트 대부분 손실",
    (AssetPart.EXTERIOR, Severity.LOW): "외관 결 유지",
    (AssetPart.EXTERIOR, Severity.MEDIUM): "표면 건조 및 색 빠짐",
    (AssetPart.EXTERIOR, Severity.HIGH): "표면 균열 및 변형",
    (AssetPart.BRACELET, Severity.LOW): "브레이슬릿 유격 없음",
    (AssetPart.BRACELET, Severity.MEDIUM): "브레이슬릿 유격 발생, 핀 교체 권장",
    (AssetPart.BRACELET, Severity.HIGH): "브레이슬릿 늘어짐 심함",
    (AssetPart.DIAL, Severity.LOW): "다이얼 청결",
    (AssetPart.DIAL, Severity.MEDIUM): "다이얼 인덱스 미세 변색",
    (AssetPart.DIAL, Severity.HIGH): "다이얼 습기 흔적",
}

#: 점수 구간 → (부위 개수, 심각도 시퀀스). 위 CATEGORY_PARTS 순서대로 배정한다.
_BANDS: tuple[tuple[int, tuple[Severity, ...]], ...] = (
    (92, ()),
    (85, (Severity.LOW,)),
    (75, (Severity.MEDIUM, Severity.LOW)),
    (70, (Severity.MEDIUM, Severity.MEDIUM)),
    (55, (Severity.HIGH, Severity.MEDIUM)),
    (0, (Severity.HIGH, Severity.HIGH, Severity.MEDIUM)),
)

YEAR_DAYS = 365.25


def stable_hash(*parts: str) -> int:
    """플랫폼·실행 간 동일한 해시.

    파이썬 `hash()` 는 문자열에 대해 매 실행 달라지므로 쓰지 않는다.
    """
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()  # noqa: S324 - 보안용 아님
    return int(digest[:12], 16)


def usage_factor(asset_id: str) -> float:
    """개체별 사용 강도(결정적)."""
    return USAGE_FACTORS[stable_hash("usage", asset_id) % len(USAGE_FACTORS)]


def years_between(purchased_at: datetime, now: datetime) -> float:
    return max(0.0, (now - purchased_at).days / YEAR_DAYS)


def condition_score(
    purchased_at: datetime,
    now: datetime,
    category: ProductCategory,
    asset_id: str,
) -> int:
    """경과 연수 × 카테고리 마모계수 × 사용강도 로 컨디션을 계산한다."""
    years = years_between(purchased_at, now)
    rate = WEAR_RATE_PER_YEAR[category]
    raw = 100.0 - years * rate * usage_factor(asset_id)
    return max(20, min(100, round(raw)))


def findings_for(score: int, category: ProductCategory) -> list[Finding]:
    """점수 구간에 따라 부위별 소견을 생성한다. 마모가 빠른 부위부터 배정."""
    parts = CATEGORY_PARTS[category]
    severities: tuple[Severity, ...] = ()
    for floor, band in _BANDS:
        if score >= floor:
            severities = band
            break
    out: list[Finding] = []
    for idx, severity in enumerate(severities):
        part = parts[idx % len(parts)]
        note = FINDING_NOTES.get((part, severity))
        if note is None:  # pragma: no cover - 표에 없는 조합 방어
            note = f"{part.value} 상태 점검 필요"
        out.append(Finding(part=part, severity=severity, note=note))
    return out


def next_service_months(score: int, category: ProductCategory, asset_id: str) -> int:
    """컨디션 70 도달까지 남은 개월 수. 이미 70 이하면 0(즉시 권장)."""
    if score <= CARE_THRESHOLD:
        return 0
    rate = WEAR_RATE_PER_YEAR[category] * usage_factor(asset_id)
    if rate <= 0:  # pragma: no cover
        return 99
    months = (score - CARE_THRESHOLD) / rate * 12.0
    return max(1, int(months))


def purchased_at_for_score(
    target_score: int, now: datetime, category: ProductCategory, asset_id: str
) -> datetime:
    """목표 컨디션 점수가 나오도록 구매 시각을 역산한다(데모 대본용 보정에 사용)."""
    from datetime import timedelta

    rate = WEAR_RATE_PER_YEAR[category] * usage_factor(asset_id)
    years = (100 - target_score) / rate
    return now - timedelta(days=years * YEAR_DAYS)


# ── 럭셔리 어휘 (결정적 리라이팅 폴백 및 LLM 프롬프트 재료) ──────────────────

LINES: tuple[str, ...] = (
    "Aurelia",
    "Solène",
    "Calisto",
    "Lisière",
    "Cadence",
    "Meridian",
    "Aubade",
    "Vesper",
    "Tessera",
    "Colline",
    "Serein",
    "Alcove",
    "Marée",
    "Petra",
    "Nocturne",
    "Halcyon",
    "Ombré",
    "Verano",
    "Rivage",
    "Étoile",
)
"""가상의 라인(제품군) 이름. 실존 브랜드명은 쓰지 않는다(상표 문제)."""

COLLECTIONS: tuple[str, ...] = (
    "Maison Nord",
    "Atelier Lumière",
    "Continuité",
    "Héritage 1948",
    "Rive Atelier",
    "Signature Noir",
)

CATEGORY_NOUNS: dict[ProductCategory, tuple[str, ...]] = {
    ProductCategory.BAG: ("Tote", "Shoulder", "Hobo", "Top Handle", "Clutch"),
    ProductCategory.SHOES: ("Derby", "Oxford", "Loafer", "Ankle Boot", "Pump"),
    ProductCategory.WATCH: ("Chronograph", "Automatic", "Ultra Thin", "Reserve"),
    ProductCategory.BELT: ("Belt", "Reversible Belt", "Corset Belt"),
    ProductCategory.WALLET: ("Long Wallet", "Card Holder", "Zip Wallet"),
    ProductCategory.OUTERWEAR: ("Trench", "Cashmere Coat", "Blouson"),
    ProductCategory.ACCESSORY: ("Scarf", "Gloves", "Charm"),
}

MATERIALS: dict[ProductCategory, tuple[str, ...]] = {
    ProductCategory.BAG: (
        "그레인 토고 카프스킨",
        "박스카프 카프스킨",
        "베지터블 탠드 새들 레더",
        "스웨이드 스플릿 스킨",
    ),
    ProductCategory.SHOES: (
        "박스카프 카프스킨 / 굿이어 웰트",
        "패티나 카프 / 블레이크 스티치",
        "스웨이드 카프 / 레더 솔",
    ),
    ProductCategory.WATCH: (
        "폴리시드 스틸 / 사파이어 크리스탈",
        "브러시드 티타늄 / 인하우스 오토매틱",
        "18K 옐로우 골드 / 매뉴얼 와인딩",
    ),
    ProductCategory.BELT: ("박스카프 카프스킨 / 팔라듐 버클", "그레인 카프 / 브러시드 버클"),
    ProductCategory.WALLET: ("에푸옴 카프스킨", "그레인 토고 카프스킨", "샤그린 엠보스 레더"),
    ProductCategory.OUTERWEAR: ("더블 캐시미어", "코튼 개버딘"),
    ProductCategory.ACCESSORY: ("실크 트윌", "램스킨"),
}

#: 카테고리별 가격 범위(원). 명세의 150만~1,200만 범위 안에서 카테고리 위계를 준다.
PRICE_BANDS: dict[ProductCategory, tuple[int, int]] = {
    ProductCategory.BAG: (3_800_000, 12_000_000),
    ProductCategory.WATCH: (4_500_000, 11_000_000),
    ProductCategory.SHOES: (1_500_000, 3_200_000),
    ProductCategory.WALLET: (1_500_000, 2_600_000),
    ProductCategory.BELT: (1_500_000, 2_200_000),
    ProductCategory.OUTERWEAR: (3_200_000, 7_500_000),
    ProductCategory.ACCESSORY: (1_500_000, 2_400_000),
}

CARE_NOTES: dict[ProductCategory, str] = {
    ProductCategory.BAG: "월 1회 무색 크림으로 보습, 핸들은 6개월마다 상태 점검 권장",
    ProductCategory.SHOES: "착화 후 슈트리 필수, 3개월마다 크림 보습 및 앞창 마모 점검",
    ProductCategory.WATCH: "2년마다 오버홀, 브레이슬릿 유격은 1년 단위 점검",
    ProductCategory.BELT: "접어 보관하지 않고 걸어 보관, 버클은 마른 천으로 관리",
    ProductCategory.WALLET: "카드 과다 수납 지양, 엣지 코트 벗겨짐은 초기 보수 권장",
    ProductCategory.OUTERWEAR: "시즌 종료 시 전문 클리닝, 통기성 커버로 보관",
    ProductCategory.ACCESSORY: "직사광선 피해 보관, 오염 시 즉시 전문 케어",
}

SIZE_SYSTEMS: dict[ProductCategory, str] = {
    ProductCategory.BAG: "Size 25 / 30 / 35 cm",
    ProductCategory.SHOES: "EU 35-42 (하프 사이즈 제작 가능)",
    ProductCategory.WATCH: "Case 38mm / 41mm",
    ProductCategory.BELT: "80 / 85 / 90 / 95 cm",
    ProductCategory.WALLET: "One size",
    ProductCategory.OUTERWEAR: "IT 44 / 46 / 48 / 50",
    ProductCategory.ACCESSORY: "One size",
}

AVAILABLE_SIZES: dict[ProductCategory, tuple[str, ...]] = {
    ProductCategory.BAG: ("25", "30", "35"),
    ProductCategory.SHOES: ("36", "37", "38", "38.5", "39", "40", "41", "42"),
    ProductCategory.WATCH: ("38mm", "41mm"),
    ProductCategory.BELT: ("80", "85", "90", "95"),
    ProductCategory.WALLET: ("One size",),
    ProductCategory.OUTERWEAR: ("44", "46", "48", "50"),
    ProductCategory.ACCESSORY: ("One size",),
}

#: 개체 지문 촬영 각도(부위) 규약. `data/fingerprints/{asset_id}/{angle}_{index}.jpg`
CAPTURE_ANGLES: dict[ProductCategory, tuple[str, ...]] = {
    ProductCategory.BAG: ("handle", "corner", "hardware", "stitching"),
    ProductCategory.SHOES: ("sole", "upper", "stitching", "edge"),
    ProductCategory.WATCH: ("dial", "bracelet", "caseback"),
    ProductCategory.BELT: ("buckle", "edge", "grain"),
    ProductCategory.WALLET: ("edge", "stitching", "interior"),
    ProductCategory.OUTERWEAR: ("collar", "cuff", "lining"),
    ProductCategory.ACCESSORY: ("surface", "edge", "label"),
}

#: styles.csv 의 (subCategory, articleType) → 우리 카테고리. 없으면 None(제외).
_ARTICLE_TO_CATEGORY: dict[str, ProductCategory] = {
    "handbags": ProductCategory.BAG,
    "clutches": ProductCategory.BAG,
    "tote bag": ProductCategory.BAG,
    "messenger bag": ProductCategory.BAG,
    "duffel bag": ProductCategory.BAG,
    "laptop bag": ProductCategory.BAG,
    "backpacks": ProductCategory.BAG,
    "rucksacks": ProductCategory.BAG,
    "trolley bag": ProductCategory.BAG,
    "waist pouch": ProductCategory.BAG,
    "wallets": ProductCategory.WALLET,
    "clutch wallet": ProductCategory.WALLET,
    "card holder": ProductCategory.WALLET,
    "watches": ProductCategory.WATCH,
    "belts": ProductCategory.BELT,
    "formal shoes": ProductCategory.SHOES,
    "casual shoes": ProductCategory.SHOES,
    "heels": ProductCategory.SHOES,
    "flats": ProductCategory.SHOES,
    "boots": ProductCategory.SHOES,
}

#: 럭셔리 톤으로 리라이팅이 어려워 명시적으로 제외하는 articleType.
_EXCLUDED_ARTICLE_TYPES: frozenset[str] = frozenset(
    {"flip flops", "sports shoes", "sports sandals", "sandals", "tshirts", "travel accessory"}
)

_SUBCATEGORY_TO_CATEGORY: dict[str, ProductCategory] = {
    "bags": ProductCategory.BAG,
    "watches": ProductCategory.WATCH,
    "belts": ProductCategory.BELT,
    "wallets": ProductCategory.WALLET,
    "shoes": ProductCategory.SHOES,
    "jackets": ProductCategory.OUTERWEAR,
}


def map_category(sub_category: str, article_type: str) -> ProductCategory | None:
    """styles.csv 분류를 우리 카테고리로 매핑한다. 대상이 아니면 None.

    articleType 이 더 구체적이므로 우선한다(예: subCategory=Bags & articleType=Wallets → WALLET).
    """
    art = (article_type or "").strip().lower()
    if art in _EXCLUDED_ARTICLE_TYPES:
        return None
    if art in _ARTICLE_TO_CATEGORY:
        return _ARTICLE_TO_CATEGORY[art]
    sub = (sub_category or "").strip().lower()
    return _SUBCATEGORY_TO_CATEGORY.get(sub)


def pick(seq: tuple[str, ...], *key: str) -> str:
    """결정적 선택. 같은 key → 항상 같은 원소."""
    return seq[stable_hash(*key) % len(seq)]


def deterministic_price(category: ProductCategory, *key: str) -> int:
    """카테고리 가격대 안에서 10만원 단위로 결정적 가격을 뽑는다."""
    low, high = PRICE_BANDS[category]
    steps = (high - low) // 100_000
    return low + (stable_hash("price", *key) % (steps + 1)) * 100_000
