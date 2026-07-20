from pydantic import BaseModel, Field

from trading_agent.domain.enums import PositionDirection


class StrategyContext(BaseModel):
    contract: str | None = None
    timeframe: str | None = None
    state_bar_closed: bool | None = None
    prior_market_state: str = "U"
    trend_score: int = 0
    price_location: str = "UNKNOWN"
    open_interest_change: float | None = None
    volume_state: str = "UNKNOWN"
    momentum_state: str = "UNKNOWN"
    price_confirmation: bool = False
    risk_status: str = "APPROVED"
    position: PositionDirection = PositionDirection.UNKNOWN
    evidence_refs: list[str] = Field(default_factory=list)
