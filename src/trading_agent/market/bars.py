from datetime import date, datetime

from math import isfinite
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator


class MarketBar(BaseModel):
    contract: str
    timeframe: str
    timestamp: datetime
    trading_date: date
    open: float = Field(gt=0, allow_inf_nan=False)
    high: float = Field(gt=0, allow_inf_nan=False)
    low: float = Field(gt=0, allow_inf_nan=False)
    close: float = Field(gt=0, allow_inf_nan=False)
    volume: float = Field(ge=0)
    open_interest: float = Field(ge=0)
    settlement: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    is_closed: bool
    source: str

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include timezone")
        return value.astimezone(ZoneInfo("Asia/Shanghai"))

    @model_validator(mode="after")
    def validate_ohlc(self) -> "MarketBar":
        values = (self.open, self.high, self.low, self.close)
        if not all(isfinite(value) for value in values):
            raise ValueError("OHLC values must be finite")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("OHLC values are inconsistent")
        if self.low > self.high:
            raise ValueError("low cannot exceed high")
        return self
