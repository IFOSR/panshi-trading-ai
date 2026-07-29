from pydantic import BaseModel, Field, model_validator

from trading_agent.domain.enums import MilestoneStatus


class MilestoneResult(BaseModel):
    number: int = Field(ge=1)
    code: str
    title: str | None = Field(default=None, min_length=1, max_length=120)
    status: MilestoneStatus
    result: str
    rule_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_conditions: list[str] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)


class StrategyEvaluation(BaseModel):
    steps: list[MilestoneResult] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_pipeline(self) -> "StrategyEvaluation":
        numbers = [step.number for step in self.steps]
        if sorted(numbers) != list(range(1, len(numbers) + 1)):
            raise ValueError(
                "strategy evaluation milestone numbers must be unique contiguous values"
            )
        return self
