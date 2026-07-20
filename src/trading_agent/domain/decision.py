from pydantic import BaseModel, Field, model_validator

from trading_agent.domain.enums import ActionType, MarketState, PositionDirection


class ActionDecision(BaseModel):
    action: ActionType
    market_state: MarketState
    position_scope: PositionDirection = PositionDirection.UNKNOWN
    supporting_steps: list[int] = Field(default_factory=list)
    blocking_steps: list[int] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    strategy: str | None = None
    signal_stage: str | None = None
    next_milestone: str | None = None
    upgrade_conditions: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_action_invariants(self) -> "ActionDecision":
        if self.action == ActionType.WAIT_FOR_DATA and not self.blocking_steps:
            raise ValueError("WAIT_FOR_DATA requires at least one blocking step")
        if self.action in {
            ActionType.HOLD,
            ActionType.ADD_CONDITIONAL,
            ActionType.REDUCE,
            ActionType.EXIT,
        } and self.position_scope in {
            PositionDirection.FLAT,
            PositionDirection.UNKNOWN,
        }:
            raise ValueError(f"{self.action.value} requires a confirmed open position")
        return self
