import os
from collections.abc import Mapping
from dataclasses import asdict
from datetime import datetime
from typing import Protocol

import httpx
from pydantic import BaseModel, Field, model_validator

from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.market.bars import MarketBar
from trading_agent.quant.atr import atr
from trading_agent.quant.boll import boll
from trading_agent.quant.confirmation import (
    MIN_PRICE_CONFIRMATION_BARS,
    classify_price_confirmation,
)
from trading_agent.quant.macd import macd
from trading_agent.vision.evidence_merger import merge_evidence


class MarketDataSnapshot(BaseModel):
    contract: str
    timeframe: str
    cutoff_time: datetime
    last_bar_closed: bool
    price_axis_verified: bool = False
    rollover_active: bool | None = None
    near_price_limit: bool | None = None
    sources: list[str] = Field(default_factory=list)
    validation_sources: list[str] = Field(default_factory=list)
    quality_issues: list[str] = Field(default_factory=list)
    contract_metadata: dict[str, object] = Field(default_factory=dict)
    blocking_issues: list[str] = Field(default_factory=list)
    bars: list[MarketBar] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_bar_identity_and_cutoff(self) -> "MarketDataSnapshot":
        ordered = sorted(self.bars, key=lambda item: item.timestamp)
        if any(item.contract != self.contract for item in ordered):
            raise ValueError("all bars must match snapshot contract")
        if any(item.timeframe != self.timeframe for item in ordered):
            raise ValueError("all bars must match snapshot timeframe")
        if ordered[-1].timestamp != self.cutoff_time:
            raise ValueError("last bar timestamp must equal snapshot cutoff")
        if any(item.timestamp > self.cutoff_time for item in ordered):
            raise ValueError("bars cannot extend beyond snapshot cutoff")
        if ordered[-1].is_closed != self.last_bar_closed:
            raise ValueError("last bar close state must match snapshot")
        return self


class MarketDataFailure(BaseModel):
    contract: str | None = None
    timeframe: str | None = None
    blocking_issues: list[str] = Field(
        default_factory=lambda: ["MARKET_DATA_UNAVAILABLE"]
    )
    quality_issues: list[str] = Field(default_factory=list)


class MarketDataResolver(Protocol):
    def resolve(
        self,
        case_state: Mapping[str, object],
        evidence: ScreenshotEvidence,
    ) -> MarketDataSnapshot | MarketDataFailure | None:
        ...


class NullMarketDataResolver:
    def resolve(
        self,
        case_state: Mapping[str, object],
        evidence: ScreenshotEvidence,
    ) -> None:
        return None


class HttpMarketDataResolver:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def resolve(
        self,
        case_state: Mapping[str, object],
        evidence: ScreenshotEvidence,
    ) -> MarketDataSnapshot | None:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        response = self.client.post(
            f"{self.base_url}/resolve",
            headers=headers,
            json={
                "case": {
                    "instrument": case_state.get("instrument"),
                    "contract": case_state.get("contract"),
                },
                "evidence": {
                    "image_role": evidence.image_role,
                    "instrument": evidence.instrument,
                    "contract": evidence.contract,
                    "timeframe": evidence.timeframe,
                    "cutoff_time": evidence.cutoff_time,
                },
            },
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return MarketDataSnapshot.model_validate(response.json())


def configured_market_data_resolver() -> MarketDataResolver:
    base_url = os.getenv("TRADING_AGENT_MARKET_DATA_URL")
    if base_url:
        return HttpMarketDataResolver(
            base_url,
            token=os.getenv("TRADING_AGENT_MARKET_DATA_TOKEN"),
        )
    provider_mode = os.getenv(
        "TRADING_AGENT_MARKET_DATA_PROVIDER",
        "none",
    ).strip().lower()
    if provider_mode == "none":
        return NullMarketDataResolver()
    if provider_mode != "free":
        raise ValueError(f"unsupported market data provider: {provider_mode}")

    from trading_agent.market.providers.akshare import AkShareMarketDataProvider
    from trading_agent.market.providers.composite import FreeMarketDataResolver
    from trading_agent.market.providers.tqsdk import TqSdkMarketDataProvider
    from trading_agent.market.providers.validation import (
        AkShareExchangeDailyValidator,
    )

    history_length = int(
        os.getenv("TRADING_AGENT_MARKET_DATA_HISTORY_LENGTH", "240")
    )
    timeout_seconds = float(
        os.getenv("TRADING_AGENT_MARKET_DATA_TIMEOUT_SECONDS", "10")
    )
    username = os.getenv("TRADING_AGENT_TQSDK_USERNAME")
    password = os.getenv("TRADING_AGENT_TQSDK_PASSWORD")
    from trading_agent.market.providers.base import MarketDataProvider

    providers: list[MarketDataProvider] = []
    if username and password:
        providers.append(
            TqSdkMarketDataProvider(
                username,
                password,
                history_length=history_length,
                timeout_seconds=timeout_seconds,
            )
        )
    providers.append(
        AkShareMarketDataProvider(timeout_seconds=timeout_seconds)
    )
    validate_exchange = os.getenv(
        "TRADING_AGENT_MARKET_DATA_VALIDATE_EXCHANGE_DAILY",
        "true",
    ).strip().lower() in {"1", "true", "yes", "on"}
    validators = (
        [AkShareExchangeDailyValidator()]
        if validate_exchange
        else []
    )
    return FreeMarketDataResolver(providers, validators=validators)


def verify_and_merge_evidence(
    evidence: ScreenshotEvidence,
    snapshot: MarketDataSnapshot | MarketDataFailure | None,
) -> ScreenshotEvidence:
    if snapshot is None:
        return evidence
    if isinstance(snapshot, MarketDataFailure):
        merged = merge_evidence(
            evidence.model_dump(mode="json"),
            {
                "contract": snapshot.contract,
                "timeframe": snapshot.timeframe,
                "blocking_issues": snapshot.blocking_issues,
                "market_data_sources": [],
                "market_data_validation_sources": [],
                "market_data_quality_issues": snapshot.quality_issues,
            },
        )
        return ScreenshotEvidence.model_validate(merged)
    merged = merge_evidence(
        evidence.model_dump(mode="json"),
        snapshot_to_verified_data(snapshot),
    )
    return ScreenshotEvidence.model_validate(merged)


def _price_location(close: float, upper: float, mid: float, lower: float) -> str:
    if close > upper:
        return "ABOVE_BOLL_UPPER"
    if close >= mid:
        return "BETWEEN_UPPER_AND_MID"
    if close >= lower:
        return "BELOW_BOLL_MID_ABOVE_LOWER"
    return "BELOW_BOLL_LOWER"


def snapshot_to_verified_data(snapshot: MarketDataSnapshot) -> dict[str, object]:
    bars = sorted(snapshot.bars, key=lambda item: item.timestamp)
    if snapshot.timeframe == "60m" and not snapshot.last_bar_closed:
        bars = [bar for bar in bars if bar.is_closed]
    latest_bar = bars[-1] if bars else None
    opens = [item.open for item in bars]
    closes = [item.close for item in bars]
    volumes = [item.volume for item in bars]
    highs = [item.high for item in bars]
    lows = [item.low for item in bars]
    base: dict[str, object] = {
        "contract": snapshot.contract,
        "timeframe": snapshot.timeframe,
        "cutoff_time": (
            latest_bar.timestamp.isoformat()
            if latest_bar
            else snapshot.cutoff_time.isoformat()
        ),
        "last_bar_closed": latest_bar.is_closed if latest_bar else False,
        "price_axis_verified": snapshot.price_axis_verified,
        "market_data_sources": snapshot.sources,
        "market_data_validation_sources": snapshot.validation_sources,
        "market_data_quality_issues": snapshot.quality_issues,
        "market_contract_metadata": snapshot.contract_metadata,
        "latest_close": latest_bar.close if latest_bar else None,
        "rollover_active": snapshot.rollover_active,
        "near_price_limit": snapshot.near_price_limit,
        "open_interest_change": (
            bars[-1].open_interest - bars[-2].open_interest
            if len(bars) >= 2
            else None
        ),
    }
    blocking_issues = list(snapshot.blocking_issues)
    if snapshot.rollover_active is None:
        blocking_issues.append("ROLLOVER_STATUS_UNKNOWN")
    if snapshot.near_price_limit is None:
        blocking_issues.append("PRICE_LIMIT_STATUS_UNKNOWN")
    blocking_issues = list(dict.fromkeys(blocking_issues))
    minimum_bars = (
        MIN_PRICE_CONFIRMATION_BARS
        if snapshot.timeframe == "60m"
        else 21
    )
    if len(bars) < minimum_bars:
        incomplete_strategy_facts: dict[str, object] = {
            "trend_bias": "UNKNOWN",
            "price_location": "UNKNOWN",
            "volume_state": "UNKNOWN",
            "momentum_state": "UNKNOWN",
        }
        if snapshot.timeframe == "60m":
            incomplete_strategy_facts.update(
                {
                    "price_confirmation": None,
                    "price_confirmation_direction": "UNKNOWN",
                    "price_confirmation_type": "UNKNOWN",
                }
            )
        return {
            **base,
            "blocking_issues": list(
                dict.fromkeys(
                    [*blocking_issues, "MARKET_HISTORY_INSUFFICIENT"]
                )
            ),
            "indicators": {},
            "strategy_facts": incomplete_strategy_facts,
        }
    boll_result = boll(closes)
    macd_result = macd(closes)
    atr_result = atr(highs, lows, closes)
    latest_dif = macd_result.dif[-1]
    latest_dea = macd_result.dea[-1]
    latest_histogram = macd_result.histogram[-1]
    if latest_dif > latest_dea and latest_dif < 0:
        momentum = "BEARISH_RECOVERY"
    elif latest_dif > latest_dea:
        momentum = "BULLISH_STRENGTHENING"
    elif latest_dif < latest_dea and latest_dif > 0:
        momentum = "BULLISH_RECOVERY"
    else:
        momentum = "BEARISH_STRENGTHENING"
    volume_short = sum(volumes[-5:]) / min(5, len(volumes))
    volume_long = sum(volumes[-10:]) / min(10, len(volumes))
    latest_volume = volumes[-1]
    if latest_volume > max(volume_short, volume_long):
        volume_state = "ABOVE_BOTH_AVERAGES"
    elif latest_volume < min(volume_short, volume_long):
        volume_state = "BELOW_BOTH_AVERAGES"
    else:
        volume_state = "BETWEEN_AVERAGES"
    trend_score = (
        (1 if closes[-1] >= boll_result.mid else -1)
        + (1 if boll_result.mid >= sum(closes[-21:-1]) / 20 else -1)
        + (1 if latest_dif >= latest_dea else -1)
    )
    trend_bias = "BULLISH" if trend_score > 0 else "BEARISH" if trend_score < 0 else "RANGE"
    indicators: dict[str, object] = {
        "boll": asdict(boll_result),
        "macd": {
            "dif": latest_dif,
            "dea": latest_dea,
            "histogram": latest_histogram,
            "fast": macd_result.fast,
            "slow": macd_result.slow,
            "signal": macd_result.signal,
            "formula_version": macd_result.formula_version,
        },
        "atr": {
            "value": atr_result.values[-1],
            "period": atr_result.period,
            "formula_version": atr_result.formula_version,
        },
    }
    strategy_facts: dict[str, object] = {
        "trend_bias": trend_bias,
        "price_location": _price_location(
            closes[-1],
            boll_result.upper,
            boll_result.mid,
            boll_result.lower,
        ),
        "volume_state": volume_state,
        "momentum_state": momentum,
    }
    if snapshot.timeframe == "60m":
        confirmation = classify_price_confirmation(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            boll_mid=boll_result.mid,
            last_bar_closed=bars[-1].is_closed,
        )
        indicators["price_confirmation"] = {
            "confirmed": confirmation.confirmed,
            "direction": confirmation.direction,
            "kind": confirmation.kind,
            "reference_price": confirmation.reference_price,
            "formula_version": "price-confirmation-range-boll-v1",
        }
        strategy_facts.update(
            {
                "price_confirmation": confirmation.confirmed,
                "price_confirmation_direction": confirmation.direction,
                "price_confirmation_type": confirmation.kind,
            }
        )
    return {
        **base,
        "blocking_issues": blocking_issues,
        "trend_score": trend_score,
        "indicators": indicators,
        "strategy_facts": strategy_facts,
    }
