from datetime import date, datetime

from pydantic import BaseModel, Field


class MarketBar(BaseModel):
    contract: str
    timeframe: str
    timestamp: datetime
    trading_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float = Field(ge=0)
    open_interest: float = Field(ge=0)
    settlement: float | None = None
    is_closed: bool
    source: str

