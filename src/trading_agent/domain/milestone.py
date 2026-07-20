from pydantic import BaseModel, Field

from trading_agent.domain.enums import MilestoneStatus


class MilestoneResult(BaseModel):
    number: int = Field(ge=1, le=8)
    code: str
    status: MilestoneStatus
    result: str
    rule_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_conditions: list[str] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)


class StrategyEvaluation(BaseModel):
    steps: list[MilestoneResult]

