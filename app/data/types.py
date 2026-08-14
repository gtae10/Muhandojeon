"""시드 데이터 타입 — 계약(contracts)의 상위집합.

`SeedProduct` 는 `contracts.common.Product` 를 상속한다. 픽스처는 `last_code` / `stock_by_size`
처럼 계약에 없는 필드를 갖는데, 상속으로 두면 **계약을 요구하는 자리에 그대로 넘길 수 있고**
(FastAPI 가 response_model 로 직렬화할 때 여분 필드는 빠진다) 상담 문구 생성처럼 더 많은 정보가
필요한 곳에서는 여분 필드를 쓸 수 있다.

`Customer` 는 계약에 없는 내부 타입이다(계약에는 `CustomerAssetsResponse.tier` 만 있다).
계약을 늘리지 않기 위해 여기에 둔다.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from contracts.common import CustomerTier, HesitationType, Product, ProductCategory, SessionEvent


class SeedProduct(Product):
    """픽스처 상품. 계약 `Product` + 사이즈 체계 코드/재고 수량."""

    last_code: str = Field(description="사이즈 체계 코드. 같은 코드면 치수가 호환된다")
    stock_by_size: dict[str, int] = Field(
        default_factory=dict, description="사이즈별 재고 수량. 0 이면 품절"
    )

    @property
    def in_stock_sizes(self) -> list[str]:
        return [size for size, qty in self.stock_by_size.items() if qty > 0]

    @property
    def total_stock(self) -> int:
        return sum(self.stock_by_size.values())

    @property
    def is_scarce(self) -> bool:
        """희소 재고 판정. 전략 S3(희소성) 문구가 사실만 말하도록 하는 근거."""
        return self.total_stock <= 2


class Customer(BaseModel):
    """픽스처 고객."""

    customer_id: str
    name: str
    tier: CustomerTier
    joined_at: datetime
    preferred_categories: list[ProductCategory] = Field(default_factory=list)
    size_profile: dict[str, str] = Field(
        default_factory=dict, description="카테고리별 고객 치수 기록 (shoes/belt/bag/watch)"
    )
    persona_binding: str | None = Field(default=None, description="바인딩된 페르소나 설명")
    note: str = ""


class ScenarioSeed(BaseModel):
    """픽스처 세션 시나리오."""

    scenario_id: str
    title: str
    label_hint: HesitationType = Field(
        description="이 시퀀스에서 규칙 엔진이 도출해야 하는 라벨(검증 대상)"
    )
    customer_id: str
    target_product_id: str
    narrative: str = ""
    events: list[SessionEvent] = Field(default_factory=list)
