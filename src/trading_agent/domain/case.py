from math import isfinite

from pydantic import BaseModel, Field, StrictInt, model_validator

from trading_agent.domain.decision import ActionDecision
from trading_agent.domain.enums import MarketState, PositionDirection
from trading_agent.domain.evidence import ScreenshotEvidence


class PositionState(BaseModel):
    direction: PositionDirection = PositionDirection.FLAT
    quantity: StrictInt = Field(default=0, ge=0)
    average_cost: float | None = None
    stop_price: float | None = None

    @model_validator(mode="after")
    def validate_position(self) -> "PositionState":
        if self.quantity == 0 and self.direction != PositionDirection.FLAT:
            raise ValueError("zero quantity requires a flat direction")
        if self.quantity > 0 and self.direction not in {
            PositionDirection.LONG,
            PositionDirection.SHORT,
        }:
            raise ValueError("open quantity requires long or short direction")
        for field_name in ("average_cost", "stop_price"):
            value = getattr(self, field_name)
            if value is not None and (not isfinite(value) or value <= 0):
                raise ValueError(f"{field_name} must be finite and positive")
        if self.quantity > 0 and self.average_cost is None:
            raise ValueError("open position requires average_cost")
        return self


class CaseState(BaseModel):
    case_id: str
    instrument: str | None = None
    contract: str | None = None
    position: PositionState = Field(default_factory=PositionState)
    lifecycle: str = "OBSERVING"
    image_ids: list[str] = Field(default_factory=list)
    analysis_ids: list[str] = Field(default_factory=list)
    parsed_images: dict[str, ScreenshotEvidence] = Field(default_factory=dict)
    current_market_state: MarketState | None = None
    signal_stage: str | None = None
    current_decision: ActionDecision | None = None
    action_history: list[str] = Field(default_factory=list)
    review_summary: str | None = None
