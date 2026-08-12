from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from trading_agent.db.base import Base


class CaseRecord(Base):
    __tablename__ = "cases"
    case_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class CaseEventRecord(Base):
    __tablename__ = "case_events"
    __table_args__ = (UniqueConstraint("case_id", "sequence"),)
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    sequence: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AnalysisRecord(Base):
    __tablename__ = "analyses"
    __table_args__ = (UniqueConstraint("case_id", "sequence"),)
    analysis_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(36), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("case_id", "command", "key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(36))
    command: Mapped[str] = mapped_column(String(40))
    key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    owner_id: Mapped[str] = mapped_column(String(36))
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class UserRecord(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AuthSessionRecord(Base):
    __tablename__ = "auth_sessions"
    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


# ---- Phase 1: Strategy Store Models ----


class StrategyRecord(Base):
    __tablename__ = "strategies"
    strategy_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    supported_markets: Mapped[list] = mapped_column(JSON, default=list)
    supported_timeframes: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="stable")
    entrypoint: Mapped[str] = mapped_column(String(240))
    input_schema_version: Mapped[str] = mapped_column(
        String(40), default="strategy-input-v1",
    )
    output_schema_version: Mapped[str] = mapped_column(
        String(40), default="strategy-result-v1",
    )
    risk_profile_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True,
    )
    process_label: Mapped[str | None] = mapped_column(
        String(120), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class StrategyVersionRecord(Base):
    __tablename__ = "strategy_versions"
    version_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(
        String(80),
        ForeignKey("strategies.strategy_id", ondelete="CASCADE"),
        index=True,
    )
    version: Mapped[str] = mapped_column(String(20))
    manifest: Mapped[dict] = mapped_column(JSON)
    pricing_type: Mapped[str] = mapped_column(
        String(20), default="free",
    )
    monthly_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    yearly_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lifetime_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="stable")
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )


class PerformanceSignalRecord(Base):
    __tablename__ = "strategy_performance_signals"
    signal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(20))
    contract: Mapped[str] = mapped_column(String(80))
    signal_date: Mapped[date] = mapped_column(Date)
    direction: Mapped[str] = mapped_column(String(20))
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )


class PerformanceSummaryRecord(Base):
    __tablename__ = "strategy_performance_summaries"
    summary_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(20))
    period: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    total_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    annualized_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_count: Mapped[int] = mapped_column(Integer, default=0)
    win_count: Mapped[int] = mapped_column(Integer, default=0)
    loss_count: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_win: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    equity_curve: Mapped[list | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ---- Phase 2: Authorization Models ----


class UserEntitlementRecord(Base):
    __tablename__ = "user_entitlements"
    entitlement_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        index=True,
    )
    strategy_id: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(20))
    access_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="active")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class OrderRecord(Base):
    __tablename__ = "orders"
    order_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        index=True,
    )
    strategy_id: Mapped[str] = mapped_column(String(80))
    version: Mapped[str] = mapped_column(String(20))
    pricing_type: Mapped[str] = mapped_column(String(20))
    subscription_period: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
    )
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    refund_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
