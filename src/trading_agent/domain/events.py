from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from trading_agent.domain.enums import PositionDirection


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CaseEvent(BaseModel):
    case_id: str
    occurred_at: datetime = Field(default_factory=utc_now)


class CaseCreated(CaseEvent):
    event_type: Literal["CASE_CREATED"] = "CASE_CREATED"
    instrument: str
    contract: str


class ImageUploaded(CaseEvent):
    event_type: Literal["IMAGE_UPLOADED"] = "IMAGE_UPLOADED"
    image_id: str
    image_path: str
    image_sha256: str


class ImageParsed(CaseEvent):
    event_type: Literal["IMAGE_PARSED"] = "IMAGE_PARSED"
    image_id: str
    evidence: dict[str, Any]


class PositionUpdated(CaseEvent):
    event_type: Literal["POSITION_UPDATED"] = "POSITION_UPDATED"
    direction: PositionDirection
    quantity: int = Field(ge=0)
    average_cost: float | None = None
    stop_price: float | None = None

    @model_validator(mode="after")
    def validate_position(self) -> "PositionUpdated":
        if self.quantity == 0 and self.direction not in {
            PositionDirection.FLAT,
            PositionDirection.UNKNOWN,
        }:
            raise ValueError("zero quantity requires a flat or unknown direction")
        if self.quantity > 0 and self.direction in {
            PositionDirection.FLAT,
            PositionDirection.UNKNOWN,
        }:
            raise ValueError("open quantity requires long or short direction")
        return self


class AnalysisIssued(CaseEvent):
    event_type: Literal["ADVICE_ISSUED"] = "ADVICE_ISSUED"
    analysis_id: str
    decision: dict[str, Any]


TradingCaseEvent = CaseCreated | ImageUploaded | ImageParsed | PositionUpdated | AnalysisIssued

