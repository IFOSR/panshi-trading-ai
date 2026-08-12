"""Pydantic models for the strategy store."""

from pydantic import BaseModel

from trading_agent.performance.models import PerformanceSummaryResponse


class RecentPerformancePreview(BaseModel):
    period: str = "近3个月"
    total_return: float | None = None
    signal_count: int = 0
    win_rate: float | None = None
    max_drawdown: float | None = None


class StrategyPricingInfo(BaseModel):
    type: str = "free"
    monthly_price: int | None = None
    yearly_price: int | None = None
    lifetime_price: int | None = None


class StrategyCard(BaseModel):
    strategy_id: str
    version: str
    display_name: str
    category: str | None = None
    supported_markets: list[str] = []
    supported_timeframes: list[str] = []
    pricing: StrategyPricingInfo | None = None
    recent_performance: RecentPerformancePreview | None = None


class StrategyDetail(StrategyCard):
    description: str | None = None
    status: str = "stable"
    recent_performance: PerformanceSummaryResponse | None = None  # type: ignore[assignment]
