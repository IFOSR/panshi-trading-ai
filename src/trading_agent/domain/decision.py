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
        for steps in (self.supporting_steps, self.blocking_steps):
            if len(steps) != len(set(steps)):
                raise ValueError("milestone references must be unique")
            if any(step < 1 or step > 8 for step in steps):
                raise ValueError("milestone references must be between 1 and 8")
        if set(self.supporting_steps) & set(self.blocking_steps):
            raise ValueError("supporting and blocking steps must be disjoint")
        if self.action == ActionType.WAIT_FOR_DATA and not self.blocking_steps:
            raise ValueError("WAIT_FOR_DATA requires at least one blocking step")
        if self.action == ActionType.ENTER_CONDITIONAL:
            required_steps = {1, 2, 3, 7, 8}
            if (
                self.market_state == MarketState.U
                or self.position_scope != PositionDirection.FLAT
                or self.blocking_steps
                or not self.strategy
                or not self.signal_stage
                or not required_steps.issubset(self.supporting_steps)
            ):
                raise ValueError(
                    "ENTER_CONDITIONAL requires valid data, strategy, price confirmation, "
                    "risk approval, and a flat position"
                )
        if self.action == ActionType.ADD_CONDITIONAL and (
            self.blocking_steps
            or not self.strategy
            or not self.signal_stage
            or not {7, 8}.issubset(self.supporting_steps)
        ):
            raise ValueError("ADD_CONDITIONAL requires new confirmation and risk approval")
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
