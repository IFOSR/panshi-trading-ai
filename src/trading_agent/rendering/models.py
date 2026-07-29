from pydantic import BaseModel, Field

from trading_agent.domain.enums import ActionType, PositionDirection


class PositionBranch(BaseModel):
    scope: PositionDirection
    action: ActionType
    label: str
    guidance: str


class RenderedDecision(BaseModel):
    action: ActionType
    summary: str
    supporting_steps: list[int]
    blocking_steps: list[int]
    upgrade_conditions: list[str]
    invalidation_conditions: list[str]
    next_milestone: str | None
    data_limitations: list[str] = Field(default_factory=list)
    position_branches: list[PositionBranch] = Field(default_factory=list)


class ValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
