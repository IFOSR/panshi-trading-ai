from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from trading_agent.domain.decision import ActionDecision
from trading_agent.domain.enums import MarketState, PositionDirection
from trading_agent.domain.evidence import ScreenshotEvidence


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CaseEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_id: str
    occurred_at: datetime = Field(default_factory=utc_now)


class CaseCreated(CaseEvent):
    event_type: Literal["CASE_CREATED"] = "CASE_CREATED"
    instrument: str | None = Field(default=None, min_length=1)
    contract: str | None = Field(default=None, min_length=1)


class ContractResolved(CaseEvent):
    event_type: Literal["CONTRACT_RESOLVED"] = "CONTRACT_RESOLVED"
    instrument: str = Field(min_length=1)
    contract: str = Field(min_length=1)


class ImageUploaded(CaseEvent):
    event_type: Literal["IMAGE_UPLOADED"] = "IMAGE_UPLOADED"
    image_id: str
    image_path: str
    image_sha256: str


class ImageParsed(CaseEvent):
    event_type: Literal["IMAGE_PARSED"] = "IMAGE_PARSED"
    image_id: str
    evidence: ScreenshotEvidence


class PositionUpdated(CaseEvent):
    event_type: Literal["POSITION_UPDATED"] = "POSITION_UPDATED"
    direction: PositionDirection
    quantity: StrictInt = Field(ge=0)
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
        for field_name in ("average_cost", "stop_price"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, (int, float)) or value <= 0):
                raise ValueError(f"{field_name} must be positive")
            if value is not None and value != value:
                raise ValueError(f"{field_name} must be finite")
        if self.quantity > 0 and self.average_cost is None:
            raise ValueError("open position requires average_cost")
        return self


class AnalysisIssued(CaseEvent):
    event_type: Literal["ADVICE_ISSUED"] = "ADVICE_ISSUED"
    analysis_id: str
    decision: ActionDecision


class MarketStateChanged(CaseEvent):
    event_type: Literal["MARKET_STATE_CHANGED"] = "MARKET_STATE_CHANGED"
    market_state: MarketState


class SignalAdvanced(CaseEvent):
    event_type: Literal["SIGNAL_ADVANCED"] = "SIGNAL_ADVANCED"
    signal_stage: str = Field(min_length=1)


class UserActionReported(CaseEvent):
    event_type: Literal["USER_ACTION_REPORTED"] = "USER_ACTION_REPORTED"
    action: str = Field(min_length=1)


class CaseClosed(CaseEvent):
    event_type: Literal["CASE_CLOSED"] = "CASE_CLOSED"
    reason: str = Field(min_length=1)


class CaseReviewed(CaseEvent):
    event_type: Literal["CASE_REVIEWED"] = "CASE_REVIEWED"
    review_summary: str = Field(min_length=1)


TradingCaseEvent = Annotated[
    Union[
        CaseCreated,
        ContractResolved,
        ImageUploaded,
        ImageParsed,
        PositionUpdated,
        MarketStateChanged,
        SignalAdvanced,
        AnalysisIssued,
        UserActionReported,
        CaseClosed,
        CaseReviewed,
    ],
    Field(discriminator="event_type"),
]
