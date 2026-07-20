from typing import Literal

from pydantic import BaseModel, Field


class RiskContext(BaseModel):
    state_bar_closed: bool | None = None
    contract_mismatch: bool = False
    rollover_active: bool = False
    near_price_limit: bool = False
    stop_distance_ratio: float | None = None
    max_stop_distance_ratio: float = 0.03
    account_risk_limit: float | None = None
    proposed_risk: float | None = None
    correlated_exposure_exceeded: bool = False
    market_state_known: bool = True


class RiskResult(BaseModel):
    status: Literal["APPROVED", "BLOCKED", "VETO"]
    reason_codes: list[str] = Field(default_factory=list)
