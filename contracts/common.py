"""모든 모듈이 공유하는 열거형과 값 객체.

이 파일의 타입은 **AI1 / AI2 / 백엔드 / 오케스트레이터가 동일하게** 쓴다.
값을 추가할 때는 `docs/CONTRACTS.md`를 다시 생성하고(`make contracts`) 팀에 공지한다.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class HesitationType(StrEnum):
    """구매 망설임 유형. AI1 의 출력 라벨이자 AI2 의 입력 조건.

    NONE 은 "망설임 신호 없음"이며, 오케스트레이터는 이 경우에도 상담을 생성한다
    (일반 제안 모드). 라벨을 늘리면 AI1 학습셋(`exports/intent_trainset.parquet`)도
    같이 갱신해야 한다.
    """

    SIZE_UNCERTAIN = "SIZE_UNCERTAIN"
    """사이즈/핏 확신 부족. size_guide 반복 조회, 동일 상품 사이즈 왕복."""
    PRICE_HESITANT = "PRICE_HESITANT"
    """가격 부담. 가격 필터 하향, 동일 카테고리 저가 상품 반복 조회."""
    STYLE_DOUBT = "STYLE_DOUBT"
    """취향/스타일 확신 부족. 여러 상품 왕복, 장시간 체류, 결정 없음."""
    STOCK_CONCERN = "STOCK_CONCERN"
    """재고/배송 불확실. 재고·배송 페이지 조회."""
    NONE = "NONE"
    """유의미한 망설임 신호 없음."""


class CTA(StrEnum):
    """상담 응답이 유도하는 다음 행동. 프론트가 버튼으로 렌더한다."""

    BOOK_FITTING = "BOOK_FITTING"
    """오프라인 피팅/방문 예약."""
    VIEW_STOCK = "VIEW_STOCK"
    """재고·입고 예정 확인."""
    CARE_BOOKING = "CARE_BOOKING"
    """케어(수선·클리닝) 예약 — 소유 자산 컨디션 근거일 때."""
    NONE = "NONE"
    """행동 유도 없음(정보 제공만)."""


class EventType(StrEnum):
    """세션 이벤트 종류.

    클릭스트림 원본에 없는 타입은 규칙 기반으로 합성한다. 어떤 필드가 원본이고
    어떤 필드가 합성인지는 `docs/DATA_PROVENANCE.md`에 명시되어 있다.
    """

    VIEW_PRODUCT = "view_product"
    IMAGE_ZOOM = "image_zoom"
    SIZE_GUIDE = "size_guide"
    PRICE_FILTER_CHANGE = "price_filter_change"
    STOCK_CHECK = "stock_check"
    SHIPPING_INFO = "shipping_info"
    CARE_INFO = "care_info"
    REVIEW_READ = "review_read"
    SEARCH = "search"
    BACK_TO_CATEGORY = "back_to_category"
    WISHLIST_ADD = "wishlist_add"
    ADD_TO_CART = "add_to_cart"
    REMOVE_FROM_CART = "remove_from_cart"
    CHECKOUT_START = "checkout_start"
    PURCHASE = "purchase"
    OTHER = "other"


class CustomerTier(StrEnum):
    """구매 이력 건수 기반 티어. NEW 1~2건 / ESTABLISHED 3~7건 / VIP 8건 이상."""

    NEW = "NEW"
    ESTABLISHED = "ESTABLISHED"
    VIP = "VIP"


class ProductCategory(StrEnum):
    """카탈로그 카테고리. 컨디션 마모 계수와 촬영 부위가 카테고리별로 다르다."""

    BAG = "BAG"
    SHOES = "SHOES"
    WATCH = "WATCH"
    BELT = "BELT"
    WALLET = "WALLET"
    OUTERWEAR = "OUTERWEAR"
    ACCESSORY = "ACCESSORY"


class AssetPart(StrEnum):
    """컨디션 소견이 가리키는 부위."""

    HANDLE = "handle"
    STITCHING = "stitching"
    CORNER = "corner"
    HARDWARE = "hardware"
    LINING = "lining"
    EXTERIOR = "exterior"
    STRAP = "strap"
    SOLE = "sole"
    UPPER = "upper"
    EDGE_COAT = "edge_coat"
    DIAL = "dial"
    BRACELET = "bracelet"


class Severity(StrEnum):
    """소견 심각도. HIGH 가 하나라도 있으면 케어 예약을 우선 제안한다."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Role(StrEnum):
    """대화 턴의 발화자."""

    CUSTOMER = "customer"
    ADVISOR = "advisor"


Confidence = Annotated[float, Field(ge=0.0, le=1.0, description="0.0~1.0 신뢰도")]
Score100 = Annotated[int, Field(ge=0, le=100, description="0~100 컨디션 점수 (100=신품)")]


class SessionEvent(BaseModel):
    """고객 세션의 단일 이벤트. AI1 입력의 기본 단위."""

    model_config = ConfigDict(extra="allow")

    event_type: EventType = Field(description="이벤트 종류")
    product_id: str | None = Field(
        default=None, description="대상 상품 id. 검색·카테고리 이벤트는 null"
    )
    timestamp: datetime = Field(description="이벤트 발생 시각 (ISO 8601, tz-aware 권장)")
    dwell_seconds: float = Field(default=0.0, ge=0.0, description="해당 화면 체류 시간(초)")
    meta: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "이벤트별 부가 정보. 예: size_guide→{'size':'38'}, "
            "price_filter_change→{'max_price_krw':3000000}, search→{'query':'...'}"
        ),
    )


class Finding(BaseModel):
    """컨디션 소견 1건. 상담 문구가 인용하는 최소 단위 근거."""

    part: AssetPart = Field(description="부위")
    severity: Severity = Field(description="심각도")
    note: str = Field(description="사람이 읽는 소견 문장 (예: '핸들 코팅 미세 균열')")


class Product(BaseModel):
    """카탈로그 상품(모델 단위). 개체(asset)와 구분한다.

    `data/processed/catalog_luxury.json` 의 레코드와 1:1 대응한다.
    """

    product_id: str = Field(description="상품 id (예: 'LX-0007')")
    name: str = Field(description="럭셔리 톤으로 리라이팅된 제품명")
    category: ProductCategory
    collection: str = Field(description="컬렉션명")
    material: str = Field(description="소재 설명")
    color: str = Field(description="컬러명")
    price_krw: int = Field(ge=0, description="정가(원). 1,500,000~12,000,000 범위")
    size_system: str = Field(description="사이즈 체계 (예: 'EU 35-42 / Last: Aurelia')")
    available_sizes: list[str] = Field(default_factory=list, description="현재 재고 사이즈")
    care_notes: str = Field(default="", description="케어 가이드 요약")
    image_path: str | None = Field(
        default=None, description="`data/processed/` 기준 상대 경로 (예: 'images/LX-0007.jpg')"
    )


class OwnedAsset(BaseModel):
    """고객이 소유한 **개체**. 개체 지문으로 식별되며 컨디션 점수를 가진다.

    이 모델이 우리 제품의 차별점이다. 상담 응답은 여기 있는 `asset_id` 를
    `cited_asset_ids` 로 인용해야 한다.
    """

    asset_id: str = Field(description="개체 id (예: 'AS-000031')")
    customer_id: str
    product_id: str
    product_name: str = Field(description="조회 편의를 위한 비정규화 필드")
    category: ProductCategory
    purchased_at: datetime = Field(description="구매 시각")
    condition_score: Score100
    findings: list[Finding] = Field(default_factory=list)
    next_service_months: int = Field(
        ge=0, description="권장 케어까지 남은 개월 수. 0 이면 즉시 권장"
    )
    last_scanned_at: datetime | None = Field(
        default=None, description="마지막 개체 지문 스캔 시각. null 이면 미등록 개체"
    )


class ChatTurn(BaseModel):
    """상담 대화 1턴."""

    role: Role
    content: str
