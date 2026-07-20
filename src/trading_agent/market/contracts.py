from enum import Enum

from pydantic import BaseModel, Field, model_validator


class ContractKind(str, Enum):
    REAL = "REAL"
    DOMINANT = "DOMINANT"
    CONTINUOUS = "CONTINUOUS"


class AdjustmentMethod(str, Enum):
    NONE = "NONE"
    FORWARD = "FORWARD"
    BACKWARD = "BACKWARD"
    RATIO = "RATIO"


class ContractSpec(BaseModel):
    instrument: str = Field(min_length=1)
    contract: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    multiplier: float = Field(gt=0)
    price_tick: float = Field(gt=0)
    kind: ContractKind = ContractKind.REAL
    adjustment_method: AdjustmentMethod = AdjustmentMethod.NONE

    @model_validator(mode="after")
    def validate_adjustment(self) -> "ContractSpec":
        if self.kind == ContractKind.CONTINUOUS and self.adjustment_method == AdjustmentMethod.NONE:
            raise ValueError("continuous contracts require an adjustment method")
        if self.kind != ContractKind.CONTINUOUS and self.adjustment_method != AdjustmentMethod.NONE:
            raise ValueError("only continuous contracts may be adjusted")
        return self

    @property
    def is_continuous(self) -> bool:
        return self.kind == ContractKind.CONTINUOUS
