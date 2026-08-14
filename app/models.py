"""SQLAlchemy 모델 — **런타임에 생성되는 데이터만** 담는다.

시드 데이터(상품·고객·개체·세션)는 DB 에 넣지 않는다. `fixtures/*.json` 이 원본이고 조회는
`app/data/provider.py` → `app/store.py` 를 경유한다. 데이터셋이 확정되면 provider 만 바꾸면
되므로 DB 스키마가 시드 구조에 묶이지 않게 하려는 것이다.

따라서 여기 있는 테이블은 셋뿐이다.
    lab_runs / lab_sessions — Persona Bot Lab 실행 결과와 대화 전문
    llm_usage              — 호출별 토큰·비용 기록 (예산 가드와 /ops 대시보드의 근거)

마이그레이션은 쓰지 않는다. 스키마를 바꾸면 `make clean-db` 로 다시 만든다
(시드가 DB 에 없으므로 지워도 잃는 것은 실행 이력뿐이다).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """선언적 베이스."""


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


class LlmUsageRow(Base):
    """LLM 호출 1건의 기록. 예산 가드가 누적액을 여기서 읽는다.

    캐시 히트와 드라이런도 기록한다. 히트율과 "캐시로 아낀 금액"을 계산해야 하기 때문이다
    (`cached=True` 인 행의 `cost_usd` 는 실제 청구액이 아니라 **아꼈을 금액**이다).
    """

    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    purpose: Mapped[str] = mapped_column(String(24), index=True)
    tier: Mapped[str] = mapped_column(String(8), default="high")
    model: Mapped[str] = mapped_column(String(64), index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    estimated: Mapped[bool] = mapped_column(
        Boolean, default=False, doc="응답 usage 가 없어 추정치를 쓴 경우"
    )
    cached: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    run_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    cache_key: Mapped[str] = mapped_column(String(40), default="")
    note: Mapped[str] = mapped_column(String(200), default="")

    @property
    def billable(self) -> bool:
        """실제 청구되는 호출인지. 캐시 히트와 드라이런은 청구되지 않는다."""
        return not self.cached and not self.dry_run
