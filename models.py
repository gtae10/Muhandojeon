"""
models.py - SQLAlchemy ORM Models
Luxury AI Clienteling Service
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Text, DateTime, 
    ForeignKey, JSON, Enum, Boolean
)
from sqlalchemy.orm import relationship, DeclarativeBase
import enum


class Base(DeclarativeBase):
    pass


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class EventType(str, enum.Enum):
    view        = "view"
    add_to_cart = "add_to_cart"
    remove_from_cart = "remove_from_cart"
    purchase    = "purchase"
    abandon     = "abandon"


class ConditionGrade(str, enum.Enum):
    mint        = "Mint"       # 90~100
    excellent   = "Excellent"  # 75~89
    good        = "Good"       # 55~74
    fair        = "Fair"       # 30~54
    poor        = "Poor"       # 0~29


class MessageRole(str, enum.Enum):
    user      = "user"
    assistant = "assistant"
    system    = "system"


# ──────────────────────────────────────────────
# Tables
# ──────────────────────────────────────────────

class User(Base):
    """고객 테이블"""
    __tablename__ = "users"

    user_id     = Column(String(36), primary_key=True, index=True)
    name        = Column(String(100), nullable=False)
    email       = Column(String(200), unique=True, nullable=False)
    tier        = Column(String(20), default="Silver")   # Bronze / Silver / Gold / Platinum
    country     = Column(String(50))
    created_at  = Column(DateTime, default=datetime.utcnow)
    is_active   = Column(Boolean, default=True)

    assets        = relationship("Asset", back_populates="owner", lazy="selectin")
    session_events = relationship("SessionEvent", back_populates="user", lazy="select")
    chat_histories = relationship("ChatHistory", back_populates="user", lazy="select")


class Product(Base):
    """럭셔리 상품 카탈로그"""
    __tablename__ = "products"

    product_id    = Column(String(36), primary_key=True, index=True)
    name          = Column(String(200), nullable=False)
    brand         = Column(String(100), nullable=False)
    category      = Column(String(50), nullable=False)   # Bag / Watch / Wallet / Jewelry / etc.
    sub_category  = Column(String(100))
    material      = Column(String(200))                  # e.g. "Monogram Canvas, Cowhide Leather"
    color         = Column(String(100))
    price_usd     = Column(Float, nullable=False)
    launch_year   = Column(Integer)
    sku           = Column(String(100), unique=True)
    image_url     = Column(Text)
    description   = Column(Text)
    extra_meta    = Column(JSON)                         # 시즌, 한정판 여부 등 확장 필드
    created_at    = Column(DateTime, default=datetime.utcnow)

    assets         = relationship("Asset", back_populates="product", lazy="select")
    session_events = relationship("SessionEvent", back_populates="product", lazy="select")


class Asset(Base):
    """고객 소유 자산 + 컨디션 상태 (핵심 테이블)"""
    __tablename__ = "assets"

    asset_id        = Column(String(36), primary_key=True, index=True)
    user_id         = Column(String(36), ForeignKey("users.user_id"), nullable=False, index=True)
    product_id      = Column(String(36), ForeignKey("products.product_id"), nullable=False)

    # 구매 이력
    purchase_date   = Column(DateTime, nullable=False)
    purchase_price  = Column(Float)                      # 실제 구매가 (할인 등 반영)
    purchase_channel = Column(String(50))                # "flagship_store" / "online" / "resale"

    # 컨디션 (개체 지문 핵심)
    condition_score = Column(Integer, nullable=False)    # 1~100
    condition_grade = Column(Enum(ConditionGrade), nullable=False)
    wear_details    = Column(JSON)                       # {"scratches": int, "cracks": int, "color_fade": bool, ...}
    last_assessed   = Column(DateTime, default=datetime.utcnow)
    notes           = Column(Text)                       # 상담사 메모

    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner   = relationship("User", back_populates="assets")
    product = relationship("Product", back_populates="assets")


class SessionEvent(Base):
    """고객 행동 로그 (망설임 탐지용)"""
    __tablename__ = "session_events"

    event_id    = Column(String(36), primary_key=True, index=True)
    user_id     = Column(String(36), ForeignKey("users.user_id"), nullable=False, index=True)
    session_id  = Column(String(36), nullable=False, index=True)
    product_id  = Column(String(36), ForeignKey("products.product_id"), nullable=True)

    event_type  = Column(Enum(EventType), nullable=False)
    event_at    = Column(DateTime, default=datetime.utcnow, index=True)
    duration_sec = Column(Float)                         # 해당 이벤트 체류 시간
    device      = Column(String(50))                     # "mobile" / "desktop" / "tablet"
    referrer    = Column(String(200))
    extra_data  = Column(JSON)                           # 추가 컨텍스트 자유 필드

    user    = relationship("User", back_populates="session_events")
    product = relationship("Product", back_populates="session_events")


class ChatHistory(Base):
    """AI 상담 이력"""
    __tablename__ = "chat_histories"

    message_id  = Column(String(36), primary_key=True, index=True)
    user_id     = Column(String(36), ForeignKey("users.user_id"), nullable=False, index=True)
    session_id  = Column(String(36), nullable=False, index=True)   # 대화 세션 단위

    role        = Column(Enum(MessageRole), nullable=False)
    content     = Column(Text, nullable=False)
    token_count = Column(Integer)
    model_used  = Column(String(50))                     # e.g. "gpt-4o"
    latency_ms  = Column(Integer)                        # 응답 지연 시간

    created_at  = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="chat_histories")
