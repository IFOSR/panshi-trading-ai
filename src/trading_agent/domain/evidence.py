from typing import Any, Literal

from pydantic import BaseModel, Field

from trading_agent.domain.enums import EvidenceUsage


class Evidence(BaseModel):
    evidence_id: str
    kind: str
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: str
    visible_text: str | None = None
    image_path: str | None = None
    evidence_description: str | None = None


class FactSupport(BaseModel):
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(min_length=1)


class StrategyEvidenceFacts(BaseModel):
    trend_bias: Literal["BULLISH", "BEARISH", "RANGE", "UNKNOWN"] = "UNKNOWN"
    price_location: Literal[
        "ABOVE_BOLL_UPPER",
        "BETWEEN_UPPER_AND_MID",
        "BELOW_BOLL_MID_ABOVE_LOWER",
        "BELOW_BOLL_LOWER",
        "AT_RANGE_SUPPORT",
        "AT_RANGE_RESISTANCE",
        "UNKNOWN",
    ] = "UNKNOWN"
    volume_state: Literal[
        "ABOVE_BOTH_AVERAGES",
        "BETWEEN_AVERAGES",
        "BELOW_BOTH_AVERAGES",
        "UNKNOWN",
    ] = "UNKNOWN"
    momentum_state: Literal[
        "BULLISH_STRENGTHENING",
        "BEARISH_STRENGTHENING",
        "BULLISH_RECOVERY",
        "BEARISH_RECOVERY",
        "DIVERGENCE",
        "UNKNOWN",
    ] = "UNKNOWN"
    position_behavior: Literal[
        "LONG_BUILD_SHORT_COVER",
        "SHORT_BUILD_LONG_EXIT",
        "POSITION_BUILDING",
        "POSITION_LIQUIDATION",
        "UNKNOWN",
    ] = "UNKNOWN"
    price_confirmation: bool | None = None
    price_confirmation_direction: Literal[
        "BULLISH", "BEARISH", "UNKNOWN"
    ] = "UNKNOWN"
    price_confirmation_type: Literal[
        "BREAKOUT",
        "HOLD",
        "PULLBACK",
        "STRUCTURAL_FAILURE",
        "UNKNOWN",
    ] = "UNKNOWN"


class ScreenshotEvidence(BaseModel):
    image_role: str
    instrument: str | None = None
    contract: str | None = None
    timeframe: str | None = None
    cutoff_time: str | None = None
    last_bar_closed: bool | None = None
    indicators: dict[str, Any] = Field(default_factory=dict)
    observations: list[Evidence] = Field(default_factory=list)
    strategy_facts: StrategyEvidenceFacts = Field(default_factory=StrategyEvidenceFacts)
    strategy_fact_support: dict[str, FactSupport] = Field(default_factory=dict)
    field_provenance: dict[str, str] = Field(default_factory=dict)
    field_evidence_refs: dict[str, list[str]] = Field(default_factory=dict)
    open_interest_change: float | None = None
    trend_score: int | None = Field(default=None, ge=-3, le=3)
    latest_close: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    rollover_active: bool = False
    near_price_limit: bool = False
    market_data_sources: list[str] = Field(default_factory=list)
    market_data_validation_sources: list[str] = Field(default_factory=list)
    market_data_quality_issues: list[str] = Field(default_factory=list)
    market_contract_metadata: dict[str, Any] = Field(default_factory=dict)
    blocking_issues: list[str] = Field(default_factory=list)
    allowed_usage: EvidenceUsage = EvidenceUsage.QUALITATIVE_ONLY
    provider: str
    model: str
    prompt_version: str
    prompt_sha256: str | None = None
    image_sha256: str
    source_image_id: str | None = None
    source_image_path: str | None = None
