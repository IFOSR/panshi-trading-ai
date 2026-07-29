from typing import Literal, Protocol

from pydantic import BaseModel, Field

from trading_agent.domain.milestone import MilestoneResult


class StrategyManifest(BaseModel):
    strategy_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,79}$")
    display_name: str = Field(min_length=1, max_length=120)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    status: Literal["stable", "test", "disabled"]
    entrypoint: str = Field(min_length=1, max_length=240)
    input_schema_version: str = "strategy-input-v1"
    output_schema_version: str = "strategy-result-v1"
    supported_markets: list[str] = Field(min_length=1)
    supported_timeframes: list[str] = Field(default_factory=list)
    process_label: str = Field(min_length=1, max_length=120)
    risk_profile_id: str = Field(min_length=1, max_length=120)


class StrategyInputSnapshot(BaseModel):
    facts: dict[str, object] = Field(default_factory=dict)
    position: str = "UNKNOWN"
    risk_constraints: dict[str, object] = Field(default_factory=dict)


class StrategySignal(BaseModel):
    market_state: str
    setup_code: str | None = None
    signal_stage: str | None = None
    data_valid: bool
    price_confirmed: bool
    supporting_steps: list[int] = Field(default_factory=list)
    blocking_steps: list[int] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    next_milestone: str | None = None
    upgrade_conditions: list[str] = Field(default_factory=list)
    invalidation_conditions: list[str] = Field(default_factory=list)


class StrategyRun(BaseModel):
    manifest: StrategyManifest
    milestones: list[MilestoneResult] = Field(min_length=1)
    signal: StrategySignal


class StrategyPlugin(Protocol):
    manifest: StrategyManifest

    def evaluate(self, snapshot: StrategyInputSnapshot) -> StrategyRun:
        ...
