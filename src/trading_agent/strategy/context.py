from pydantic import BaseModel, Field

from trading_agent.domain.enums import PositionDirection


class StrategyContext(BaseModel):
    contract: str | None = None
    timeframe: str | None = None
    state_bar_closed: bool | None = None
    data_cutoff_time: str | None = None
    data_age_seconds: float | None = Field(default=None, ge=0)
    max_data_age_seconds: float = Field(default=129_600, gt=0)
    prior_market_state: str = "U"
    trend_score: int = 0
    price_location: str = "UNKNOWN"
    open_interest_change: float | None = None
    volume_state: str = "UNKNOWN"
    position_behavior_state: str = "UNKNOWN"
    momentum_state: str = "UNKNOWN"
    price_confirmation: bool | None = None
    price_confirmation_direction: str = "UNKNOWN"
    price_confirmation_type: str = "UNKNOWN"
    risk_status: str = "APPROVED"
    position: PositionDirection = PositionDirection.UNKNOWN
    state_image_role: str | None = None
    data_blockers: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_refs_by_field: dict[str, list[str]] = Field(default_factory=dict)
    market_data_sources: list[str] = Field(default_factory=list)
    market_data_validation_sources: list[str] = Field(default_factory=list)
    market_data_quality_issues: list[str] = Field(default_factory=list)
    market_contract_metadata: dict[str, object] = Field(default_factory=dict)
    contract_mismatch: bool = False
    rollover_active: bool = False
    near_price_limit: bool = False
    stop_distance_ratio: float | None = None
    max_stop_distance_ratio: float = 0.03
    account_risk_limit: float | None = None
    proposed_risk: float | None = None
    correlated_exposure_exceeded: bool = False
    forced_exit: bool = False
    position_invalidated: bool = False
    reduce_required: bool = False
    add_confirmation: bool = False


def evidence_refs_for(context: StrategyContext, *fields: str) -> list[str]:
    return list(dict.fromkeys(
        ref
        for field in fields
        for ref in context.evidence_refs_by_field.get(field, [])
    ))
