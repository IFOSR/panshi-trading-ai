"""Order models."""

from datetime import datetime

from pydantic import BaseModel


class OrderCreateRequest(BaseModel):
    strategy_id: str
    version: str
    pricing_type: str
    subscription_period: str | None = None


class OrderResponse(BaseModel):
    order_id: str
    user_id: str
    strategy_id: str
    version: str
    pricing_type: str
    subscription_period: str | None = None
    amount: int
    currency: str = "CNY"
    status: str = "pending"
    paid_at: datetime | None = None
    created_at: datetime | None = None
    refund_reason: str | None = None
