from datetime import date
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from trading_agent.domain.milestone import MilestoneResult


# ---- Pricing & Performance ----


class StrategyPricing(BaseModel):
    type: Literal["free", "onetime", "subscription"]
    monthly_price: int | None = None
    yearly_price: int | None = None
    lifetime_price: int | None = None


class PerformanceConfig(BaseModel):
    track_enabled: bool = True
    history_days: int = Field(default=90, ge=1)
    update_cron: str = "0 16 * * 1-5"


# ---- Fact & Data Requirements ----


class FactRequirement(BaseModel):
    field: str
    label: str
    required: bool = False
    default: str | None = None
    source: list[str] = Field(default_factory=list)
    description: str = ""


class DataRequirement(BaseModel):
    type: str
    timeframe: str | None = None
    length: int | None = None
    categories: list[str] | None = None


# ---- Performance Track ----


class PerformanceSignalRecord_pydantic(BaseModel):
    contract: str
    signal_date: date
    direction: str
    entry_price: float | None = None
    exit_price: float | None = None
    return_pct: float | None = None
    status: str = "closed"
    closed_date: date | None = None


class PerformanceTrack(BaseModel):
    strategy_id: str
    version: str
    start_date: date
    end_date: date
    signals: list[dict] = Field(min_length=1)
    summary: dict


# ---- Strategy Manifest ----


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
    # Phase 1: commercialization fields
    pricing: StrategyPricing | None = None
    performance_config: PerformanceConfig | None = None


# ---- Strategy Input ----


class StrategyInputSnapshot(BaseModel):
    facts: dict[str, object] = Field(default_factory=dict)
    position: str = "UNKNOWN"
    risk_constraints: dict[str, object] = Field(default_factory=dict)


# ---- Strategy Signal ----


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


# ---- Strategy Run ----


class StrategyRun(BaseModel):
    manifest: StrategyManifest
    milestones: list[MilestoneResult] = Field(min_length=1)
    signal: StrategySignal


# ---- Strategy Plugin Protocol ----


class StrategyPlugin(Protocol):
    manifest: StrategyManifest

    def evaluate(self, snapshot: StrategyInputSnapshot) -> StrategyRun:
        ...

    def required_facts(self, context: dict) -> list[FactRequirement]:
        ...

    def required_data(self, context: dict) -> list[DataRequirement]:
        ...

    def track_performance(
        self,
        start_date: date,
        end_date: date,
        market_data: dict | None = None,
    ) -> PerformanceTrack:
        ...
