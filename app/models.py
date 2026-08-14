"""SQLAlchemy 모델 — 해커톤용 SQLite 스키마.

마이그레이션은 쓰지 않는다. 스키마를 바꾸면 `make clean-db && make seed` 로 다시 만든다
(정규화 산출물 `data/processed/*.json` 이 원본 역할을 하므로 언제든 재현된다).

`data/processed/*.json` 이 사실의 원본이고 SQLite 는 조회 편의를 위한 사본이다.
목 어댑터는 JSON 을 직접 읽고, Persona Bot Lab 결과처럼 **런타임에 생성되는 데이터만**
SQLite 에만 존재한다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """선언적 베이스."""


class ProductRow(Base):
    """카탈로그 상품 (모델 단위)."""

    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(16), index=True)
    collection: Mapped[str] = mapped_column(String(80))
    material: Mapped[str] = mapped_column(String(160))
    color: Mapped[str] = mapped_column(String(40))
    price_krw: Mapped[int] = mapped_column(Integer, index=True)
    size_system: Mapped[str] = mapped_column(String(120))
    available_sizes: Mapped[list[str]] = mapped_column(JSON, default=list)
    care_notes: Mapped[str] = mapped_column(Text, default="")
    image_path: Mapped[str | None] = mapped_column(String(200), nullable=True)

    assets: Mapped[list[AssetRow]] = relationship(back_populates="product")


class CustomerRow(Base):
    """고객."""

    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(40))
    tier: Mapped[str] = mapped_column(String(16), index=True)
    purchase_count: Mapped[int] = mapped_column(Integer, default=0)
    asset_count: Mapped[int] = mapped_column(Integer, default=0)

    assets: Mapped[list[AssetRow]] = relationship(back_populates="customer")


class AssetRow(Base):
    """소유 개체. 개체 지문으로 식별되는 단위."""

    __tablename__ = "assets"

    asset_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.product_id"), index=True)
    product_name: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(16))
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    condition_score: Mapped[int] = mapped_column(Integer, index=True)
    findings: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    next_service_months: Mapped[int] = mapped_column(Integer, index=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer: Mapped[CustomerRow] = relationship(back_populates="assets")
    product: Mapped[ProductRow] = relationship(back_populates="assets")
    fingerprints: Mapped[list[FingerprintRow]] = relationship(back_populates="asset")


class SessionRow(Base):
    """이탈 세션 + 망설임 라벨 (데모 입력이자 AI1 학습셋의 사본)."""

    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(16), index=True)
    customer_tier: Mapped[str] = mapped_column(String(16))
    target_product_id: Mapped[str] = mapped_column(String(16), index=True)
    hesitation_label: Mapped[str] = mapped_column(String(24), index=True)
    label_rule: Mapped[str] = mapped_column(String(80))
    label_confidence: Mapped[float] = mapped_column(Float)
    profile: Mapped[str] = mapped_column(String(16))
    abandoned: Mapped[bool] = mapped_column(Boolean, default=True)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    signals: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class FingerprintRow(Base):
    """개체 지문 이미지 등록 기록. 임베딩은 백엔드 담당 몫이라 여기엔 없다."""

    __tablename__ = "fingerprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[str] = mapped_column(ForeignKey("assets.asset_id"), index=True)
    angle: Mapped[str] = mapped_column(String(24), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(240), unique=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    blur_score: Mapped[float] = mapped_column(Float)
    brightness: Mapped[float] = mapped_column(Float)
    brightness_std: Mapped[float] = mapped_column(Float)
    passed: Mapped[bool] = mapped_column(Boolean, index=True)
    reason: Mapped[str] = mapped_column(String(200), default="")
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    asset: Mapped[AssetRow] = relationship(back_populates="fingerprints")


class LabRunRow(Base):
    """Persona Bot Lab 실행 1회(45세션 묶음)."""

    __tablename__ = "lab_runs"

    run_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    total_sessions: Mapped[int] = mapped_column(Integer, default=0)
    completed_sessions: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)

    sessions: Mapped[list[LabSessionRow]] = relationship(back_populates="run")


class LabSessionRow(Base):
    """페르소나 × 전략 × 반복 1회의 시뮬레이션 결과. 대화 전문을 보관한다."""

    __tablename__ = "lab_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("lab_runs.run_id"), index=True)
    persona_id: Mapped[str] = mapped_column(String(8), index=True)
    strategy_id: Mapped[str] = mapped_column(String(8), index=True)
    iteration: Mapped[int] = mapped_column(Integer)
    customer_id: Mapped[str] = mapped_column(String(16))
    target_product_id: Mapped[str] = mapped_column(String(16))
    hesitation_type: Mapped[str] = mapped_column(String(24))

    converted: Mapped[bool] = mapped_column(Boolean, index=True)
    turns_to_decision: Mapped[int] = mapped_column(Integer)
    drop_reason: Mapped[str] = mapped_column(String(40), index=True, default="")
    trust_score: Mapped[int] = mapped_column(Integer)
    judge_reasoning: Mapped[str] = mapped_column(Text, default="")

    cited_asset_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    owned_assets_used: Mapped[bool] = mapped_column(Boolean, index=True, default=False)
    transcript: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    degraded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    run: Mapped[LabRunRow] = relationship(back_populates="sessions")
