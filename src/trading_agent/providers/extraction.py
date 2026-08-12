"""Shared screenshot extraction models used by multimodal providers."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from trading_agent.domain.enums import EvidenceUsage


class StrictExtractionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BollExtraction(StrictExtractionModel):
    period: int | None
    mid: float | None = Field(allow_inf_nan=False)
    upper: float | None = Field(allow_inf_nan=False)
    lower: float | None = Field(allow_inf_nan=False)


class MacdExtraction(StrictExtractionModel):
    fast: int | None
    slow: int | None
    signal: int | None
    dif: float | None = Field(allow_inf_nan=False)
    dea: float | None = Field(allow_inf_nan=False)
    histogram: float | None = Field(allow_inf_nan=False)


class VolumeExtraction(StrictExtractionModel):
    current: float | None = Field(allow_inf_nan=False)
    ma_short: float | None = Field(allow_inf_nan=False)
    ma_long: float | None = Field(allow_inf_nan=False)


class PositionBehaviorExtraction(StrictExtractionModel):
    label: str | None = Field(max_length=80)
    value: float | None = Field(allow_inf_nan=False)
    interpretation: str | None = Field(max_length=500)


class StrategyFactsExtraction(StrictExtractionModel):
    trend_bias: str = Field(pattern="^(BULLISH|BEARISH|RANGE|UNKNOWN)$")
    price_location: str = Field(
        pattern=(
            "^(ABOVE_BOLL_UPPER|BETWEEN_UPPER_AND_MID|"
            "BELOW_BOLL_MID_ABOVE_LOWER|BELOW_BOLL_LOWER|"
            "AT_RANGE_SUPPORT|AT_RANGE_RESISTANCE|UNKNOWN)$"
        )
    )
    volume_state: str = Field(
        pattern="^(ABOVE_BOTH_AVERAGES|BETWEEN_AVERAGES|BELOW_BOTH_AVERAGES|UNKNOWN)$"
    )
    momentum_state: str = Field(
        pattern=(
            "^(BULLISH_STRENGTHENING|BEARISH_STRENGTHENING|"
            "BULLISH_RECOVERY|BEARISH_RECOVERY|DIVERGENCE|UNKNOWN)$"
        )
    )
    position_behavior: str = Field(
        pattern=(
            "^(LONG_BUILD_SHORT_COVER|SHORT_BUILD_LONG_EXIT|"
            "POSITION_BUILDING|POSITION_LIQUIDATION|UNKNOWN)$"
        )
    )
    price_confirmation: bool | None
    price_confirmation_direction: str = Field(
        pattern="^(BULLISH|BEARISH|UNKNOWN)$"
    )
    price_confirmation_type: str = Field(
        pattern="^(BREAKOUT|HOLD|PULLBACK|STRUCTURAL_FAILURE|UNKNOWN)$"
    )


class FactSupportExtraction(StrictExtractionModel):
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(min_length=1)


class StrategyFactSupportExtraction(StrictExtractionModel):
    trend_bias: FactSupportExtraction | None
    price_location: FactSupportExtraction | None
    volume_state: FactSupportExtraction | None
    momentum_state: FactSupportExtraction | None
    position_behavior: FactSupportExtraction | None
    price_confirmation: FactSupportExtraction | None
    price_confirmation_direction: FactSupportExtraction | None
    price_confirmation_type: FactSupportExtraction | None


class IndicatorExtraction(StrictExtractionModel):
    boll: BollExtraction | None
    macd: MacdExtraction | None
    volume: VolumeExtraction | None
    position_behavior: PositionBehaviorExtraction | None
    notes: list[str]


class ObservationExtraction(StrictExtractionModel):
    evidence_id: str = Field(min_length=1, max_length=100)
    kind: str = Field(min_length=1, max_length=100)
    conclusion: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    visible_text: str | None = Field(max_length=500)
    evidence_description: str = Field(min_length=1, max_length=1000)
    source_image_index: int = Field(ge=0)


class ScreenshotExtraction(StrictExtractionModel):
    image_role: str = Field(pattern="^(STATE_DAILY|EXECUTION_60M|MEMBER_POSITION|CONTRACT_ROLLOVER|ACCOUNT_POSITION|AUXILIARY)$")
    instrument: str | None = Field(max_length=80)
    contract: str | None = Field(max_length=40)
    timeframe: str | None = Field(pattern="^(1d|D1|60m|1h|H1)$")
    cutoff_time: str | None = Field(max_length=40)
    last_bar_closed: bool | None
    indicators: IndicatorExtraction
    strategy_facts: StrategyFactsExtraction
    strategy_fact_support: StrategyFactSupportExtraction
    observations: list[ObservationExtraction]
    blocking_issues: list[str]
    allowed_usage: EvidenceUsage

    @field_validator("cutoff_time")
    @classmethod
    def validate_cutoff_time(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from datetime import date, datetime

        normalized = value.replace("/", "-")
        if len(normalized) == 10:
            date.fromisoformat(normalized)
            return normalized
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            from zoneinfo import ZoneInfo

            parsed = parsed.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return parsed.isoformat()


def enforce_safe_usage(extraction: ScreenshotExtraction) -> EvidenceUsage:
    if extraction.allowed_usage == EvidenceUsage.EXACT:
        return EvidenceUsage.QUALITATIVE_ONLY
    return extraction.allowed_usage
