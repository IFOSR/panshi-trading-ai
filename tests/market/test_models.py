from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from trading_agent.market.bars import MarketBar
from trading_agent.market.contracts import AdjustmentMethod, ContractKind, ContractSpec


def test_contract_requires_adjustment_for_continuous_series() -> None:
    with pytest.raises(ValidationError):
        ContractSpec(
            instrument="rb",
            contract="rb888",
            exchange="SHFE",
            multiplier=10,
            price_tick=1,
            kind=ContractKind.CONTINUOUS,
            adjustment_method=AdjustmentMethod.NONE,
        )


def test_market_bar_rejects_impossible_ohlc_and_naive_time() -> None:
    with pytest.raises(ValidationError):
        MarketBar(
            contract="rb2610",
            timeframe="1h",
            timestamp=datetime(2026, 7, 20, 10, 0),
            trading_date=date(2026, 7, 20),
            open=3500,
            high=3490,
            low=3480,
            close=3501,
            volume=100,
            open_interest=200,
            is_closed=True,
            source="fixture",
        )


def test_market_bar_normalizes_to_shanghai_timezone() -> None:
    bar = MarketBar(
        contract="rb2610",
        timeframe="1h",
        timestamp=datetime(2026, 7, 20, 2, 0, tzinfo=ZoneInfo("UTC")),
        trading_date=date(2026, 7, 20),
        open=3500,
        high=3520,
        low=3490,
        close=3510,
        volume=100,
        open_interest=200,
        is_closed=True,
        source="fixture",
    )

    assert bar.timestamp.hour == 10
    assert str(bar.timestamp.tzinfo) == "Asia/Shanghai"
