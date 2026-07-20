from pydantic import BaseModel, Field


class ContractSpec(BaseModel):
    instrument: str = Field(min_length=1)
    contract: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    multiplier: float = Field(gt=0)
    price_tick: float = Field(gt=0)
    is_continuous: bool = False
    adjustment_method: str | None = None

