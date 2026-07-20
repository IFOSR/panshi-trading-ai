from pydantic import BaseModel, Field

from trading_agent.domain.enums import PositionDirection


class PositionState(BaseModel):
    direction: PositionDirection = PositionDirection.FLAT
    quantity: int = Field(default=0, ge=0)
    average_cost: float | None = None
    stop_price: float | None = None


class CaseState(BaseModel):
    case_id: str
    instrument: str
    contract: str
    position: PositionState = Field(default_factory=PositionState)
    lifecycle: str = "OBSERVING"
    image_ids: list[str] = Field(default_factory=list)
    analysis_ids: list[str] = Field(default_factory=list)

