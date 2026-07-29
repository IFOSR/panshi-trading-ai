from typing import Literal

from pydantic import BaseModel, Field, model_validator


ClarificationField = str


class ClarificationQuestion(BaseModel):
    question_id: str
    field: ClarificationField
    allowed_fact_fields: list[str] = Field(default_factory=list)
    milestone_number: int = Field(ge=1)
    uncertainty: str
    question: str
    answer_examples: list[str] = Field(min_length=1)
    blocking_issues: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def default_allowed_fact_fields(self) -> "ClarificationQuestion":
        if not self.allowed_fact_fields:
            self.allowed_fact_fields = (
                [
                    "price_confirmation",
                    "price_confirmation_direction",
                    "price_confirmation_type",
                ]
                if self.field == "price_confirmation"
                else [self.field]
            )
        return self


class ClarificationFact(BaseModel):
    question_id: str
    field: ClarificationField
    value: bool | float | str
    explanation: str = Field(min_length=1, max_length=500)
    resolves_blockers: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_value_for_field(self) -> "ClarificationFact":
        if self.field in {"state_bar_closed", "execution_bar_closed", "price_confirmation"}:
            if not isinstance(self.value, bool):
                raise ValueError(f"{self.field} requires a boolean value")
        elif self.field == "open_interest_change":
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise ValueError("open_interest_change requires a numeric value")
        elif self.field == "position_behavior_state":
            allowed = {
                "LONG_BUILD_SHORT_COVER",
                "SHORT_BUILD_LONG_EXIT",
                "POSITION_BUILDING",
                "POSITION_LIQUIDATION",
            }
            if self.value not in allowed:
                raise ValueError("unsupported position_behavior_state")
        elif self.field == "price_confirmation_direction":
            if self.value not in {"BULLISH", "BEARISH"}:
                raise ValueError("unsupported price_confirmation_direction")
        elif self.field == "price_confirmation_type":
            if self.value not in {
                "BREAKOUT",
                "HOLD",
                "PULLBACK",
                "STRUCTURAL_FAILURE",
            }:
                raise ValueError("unsupported price_confirmation_type")
        elif (
            self.field in {"contract", "timeframe", "cutoff_time"}
            and (not isinstance(self.value, str) or not self.value.strip())
        ):
            raise ValueError(f"{self.field} requires a non-empty string")
        elif not isinstance(self.value, (bool, int, float, str)):
            raise ValueError(f"{self.field} has an unsupported value")
        elif isinstance(self.value, str) and not self.value.strip():
            raise ValueError(f"{self.field} requires a non-empty string")
        return self


class ClarificationProposal(BaseModel):
    clarification_id: str
    source_analysis_id: str
    user_message: str = Field(min_length=1, max_length=4000)
    facts: list[ClarificationFact]
    unresolved_question_ids: list[str] = Field(default_factory=list)
    interpretation: str = Field(min_length=1, max_length=2000)
    provider: str
    model: str
    status: Literal["PENDING_CONFIRMATION"] = "PENDING_CONFIRMATION"


class ClarificationHistoryItem(BaseModel):
    clarification_id: str
    source_analysis_id: str
    user_message: str
    facts: list[ClarificationFact]
    unresolved_question_ids: list[str] = Field(default_factory=list)
    interpretation: str
    provider: str
    model: str
    status: Literal["PENDING_CONFIRMATION", "CONFIRMED"]
    confirmed_at: str | None = None
    result_analysis_id: str | None = None
