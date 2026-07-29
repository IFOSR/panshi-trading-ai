from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.market.bars import MarketBar
from trading_agent.market.providers.validation import AkShareExchangeDailyValidator
from trading_agent.market.resolver import (
    MarketDataSnapshot,
    verify_and_merge_evidence,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def snapshot() -> MarketDataSnapshot:
    start = datetime(2026, 7, 3, 15, 0, tzinfo=SHANGHAI)
    bars = [
        MarketBar(
            contract="rb2610",
            timeframe="1d",
            timestamp=start + timedelta(days=index),
            trading_date=date(2026, 7, 3) + timedelta(days=index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=1000 + index,
            open_interest=5000 + index,
            settlement=101 + index,
            is_closed=True,
            source="tqsdk",
        )
        for index in range(21)
    ]
    return MarketDataSnapshot(
        contract="rb2610",
        timeframe="1d",
        cutoff_time=bars[-1].timestamp,
        last_bar_closed=True,
        price_axis_verified=True,
        sources=["tqsdk"],
        contract_metadata={
            "exchange": "SHFE",
            "price_tick": 1.0,
        },
        bars=bars,
    )


class FakeExchangeData:
    def __init__(self, frame: pd.DataFrame | None) -> None:
        self.frame = frame
        self.calls: list[tuple[str, str, str]] = []

    def get_futures_daily(self, start_date, end_date, market):
        self.calls.append((start_date, end_date, market))
        if self.frame is None:
            raise RuntimeError("exchange report unavailable")
        return self.frame


def official_row(**updates) -> pd.DataFrame:
    values = {
        "symbol": "RB2610",
        "date": "20260723",
        "open": 120.0,
        "high": 122.0,
        "low": 119.0,
        "close": 121.0,
        "volume": 1020,
        "open_interest": 5020,
        "settle": 121.0,
    }
    values.update(updates)
    return pd.DataFrame([values])


def test_matching_exchange_daily_data_records_validation_source() -> None:
    module = FakeExchangeData(official_row())
    validator = AkShareExchangeDailyValidator(module=module)

    result = validator.validate(snapshot())

    assert result.validation_sources == ["SHFE_OFFICIAL_DAILY"]
    assert result.blocking_issues == []
    assert module.calls == [("20260723", "20260723", "SHFE")]


def test_unavailable_exchange_report_is_a_non_blocking_quality_issue() -> None:
    validator = AkShareExchangeDailyValidator(
        module=FakeExchangeData(None)
    )

    result = validator.validate(snapshot())

    assert result.price_axis_verified is True
    assert result.blocking_issues == []
    assert result.quality_issues == ["SHFE_OFFICIAL_DAILY_UNAVAILABLE"]


def test_malformed_exchange_values_are_a_non_blocking_quality_issue() -> None:
    validator = AkShareExchangeDailyValidator(
        module=FakeExchangeData(official_row(close="-"))
    )

    result = validator.validate(snapshot())

    assert result.price_axis_verified is True
    assert result.blocking_issues == []
    assert result.quality_issues == ["SHFE_OFFICIAL_DAILY_UNAVAILABLE"]


def test_exchange_conflict_blocks_exact_structured_evidence() -> None:
    validator = AkShareExchangeDailyValidator(
        module=FakeExchangeData(official_row(close=125.0))
    )

    resolution = validator.validate(snapshot())
    merged = verify_and_merge_evidence(
        ScreenshotEvidence(
            image_role="STATE_DAILY",
            contract="rb2610",
            timeframe="1d",
            provider="codex",
            model="gpt-5.6-sol",
            prompt_version="chart-evidence-v2",
            image_sha256="fixture",
        ),
        resolution,
    )

    assert resolution.price_axis_verified is False
    assert "MARKET_DATA_VALIDATION_CONFLICT" in merged.blocking_issues
    assert merged.allowed_usage.value == "QUALITATIVE_ONLY"
