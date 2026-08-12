"""FactExtractor models."""

from enum import Enum

from pydantic import BaseModel, Field

from trading_agent.strategies.contracts import FactRequirement


class ExtractionStatus(str, Enum):
    COMPLETE = "complete"
    MISSING_INFO = "missing_info"
    ERROR = "error"


class FactExtractionResult(BaseModel):
    status: ExtractionStatus
    extracted_facts: dict[str, str | None] = Field(default_factory=dict)
    missing_fields: list[FactRequirement] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    strategy_id: str = ""
    version: str = ""
