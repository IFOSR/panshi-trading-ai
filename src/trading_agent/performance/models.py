"""Pydantic models for performance tracking responses."""

from datetime import date

from pydantic import BaseModel, Field


class PerformanceSignalItem(BaseModel):
    contract: str
    signal_date: date
    direction: str
    entry_price: float | None = None
    exit_price: float | None = None
    return_pct: float | None = None
    status: str = "closed"
    closed_date: date | None = None
    evidence: dict | None = None


class PerformanceSummaryResponse(BaseModel):
    strategy_id: str
    version: str
    period: str = "近3个月"
    start_date: date
    end_date: date
    total_return: float | None = None
    annualized_return: float | None = None
    max_drawdown: float | None = None
    signal_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float | None = None
    avg_win: float | None = None
    avg_loss: float | None = None
    equity_curve: list | None = None
    signals: list[PerformanceSignalItem] = Field(default_factory=list)
