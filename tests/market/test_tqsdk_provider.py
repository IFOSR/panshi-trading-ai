from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

from trading_agent.market.providers.base import MarketDataRequest
from trading_agent.market.providers.tqsdk import TqSdkMarketDataProvider


SHANGHAI = ZoneInfo("Asia/Shanghai")


def ns(value: str) -> int:
    return int(pd.Timestamp(value, tz=SHANGHAI).timestamp() * 1_000_000_000)


class FakeTqApi:
    def __init__(self, klines: pd.DataFrame, now: datetime) -> None:
        self.klines = klines
        self.now = now
        self.closed = False
        self.requested_product: str | None = None
        self.requested_duration: int | None = None

    def query_quotes(self, **kwargs):
        self.requested_product = kwargs["product_id"]
        return ["SHFE.rb2610"]

    def query_symbol_info(self, symbol):
        assert symbol == "SHFE.rb2610"
        return pd.DataFrame(
            [
                {
                    "instrument_id": symbol,
                    "exchange_id": "SHFE",
                    "product_id": "rb",
                    "price_tick": 1.0,
                    "volume_multiple": 10,
                    "upper_limit": 3400.0,
                    "lower_limit": 2800.0,
                    "pre_settlement": 3090.0,
                    "expire_datetime": int(
                        datetime(2026, 10, 15, tzinfo=SHANGHAI).timestamp()
                    ),
                    "trading_time_day": [["09:00:00", "10:15:00"], ["10:30:00", "15:00:00"]],
                    "trading_time_night": [["21:00:00", "23:00:00"]],
                }
            ]
        )

    def get_kline_serial(self, symbol, duration_seconds, data_length):
        assert symbol == "SHFE.rb2610"
        self.requested_duration = duration_seconds
        assert data_length == 240
        return self.klines

    def get_quote(self, symbol):
        assert symbol == "KQ.m@SHFE.rb"
        return type("Quote", (), {"underlying_symbol": "SHFE.rb2610"})()

    def get_trading_calendar(self, start_dt, end_dt):
        return pd.DataFrame(
            [
                {"date": pd.Timestamp("2026-07-22"), "trading": True},
                {"date": pd.Timestamp("2026-07-23"), "trading": True},
                {"date": pd.Timestamp("2026-07-24"), "trading": True},
            ]
        )

    def query_symbol_settlement(self, symbol, days, start_dt=None):
        return pd.DataFrame(
            [
                {
                    "instrument_id": symbol,
                    "trading_day": pd.Timestamp("2026-07-22"),
                    "settlement": 3083.0,
                },
                {
                    "instrument_id": symbol,
                    "trading_day": pd.Timestamp("2026-07-23"),
                    "settlement": 3090.0,
                },
            ]
        )

    def wait_update(self, deadline=None):
        return True

    def close(self):
        self.closed = True


def test_tqsdk_normalizes_closed_daily_bars_and_contract_metadata() -> None:
    frame = pd.DataFrame(
        [
            {
                "id": 1,
                "datetime": ns("2026-07-21 21:00:00"),
                "open": 3070.0,
                "high": 3090.0,
                "low": 3060.0,
                "close": 3083.0,
                "volume": 1000,
                "open_oi": 1800000,
                "close_oi": 1810000,
            },
            {
                "id": 2,
                "datetime": ns("2026-07-22 21:00:00"),
                "open": 3083.0,
                "high": 3108.0,
                "low": 3078.0,
                "close": 3085.0,
                "volume": 1200,
                "open_oi": 1810000,
                "close_oi": 1872417,
            },
        ]
    )
    api = FakeTqApi(
        frame,
        datetime(2026, 7, 23, 16, 0, tzinfo=SHANGHAI),
    )
    provider = TqSdkMarketDataProvider(
        "free-user",
        "free-password",
        api_factory=lambda: api,
        clock=lambda: api.now,
    )

    result = provider.fetch(
        MarketDataRequest(
            contract="rb2610",
            timeframe="1d",
            image_role="STATE_DAILY",
        )
    )

    assert result is not None
    assert api.requested_product == "rb"
    assert api.requested_duration == 86400
    assert result.contract == "rb2610"
    assert result.last_bar_closed is True
    assert result.bars[-1].trading_date == date(2026, 7, 23)
    assert result.bars[-1].open_interest == 1872417
    assert result.bars[-1].settlement == 3090.0
    assert result.contract_metadata == {
        "exchange": "SHFE",
        "provider_symbol": "SHFE.rb2610",
        "product": "rb",
        "price_tick": 1.0,
        "multiplier": 10,
        "upper_limit": 3400.0,
        "lower_limit": 2800.0,
        "pre_settlement": 3090.0,
        "expire_datetime": "2026-10-15T00:00:00+08:00",
        "trading_time_day": [["09:00:00", "10:15:00"], ["10:30:00", "15:00:00"]],
        "trading_time_night": [["21:00:00", "23:00:00"]],
        "dominant_contract": "SHFE.rb2610",
    }
    assert result.rollover_active is False
    assert result.sources == ["tqsdk"]
    assert api.closed is True


def test_tqsdk_marks_the_current_60_minute_bar_unclosed_during_session() -> None:
    frame = pd.DataFrame(
        [
            {
                "id": 1,
                "datetime": ns("2026-07-23 09:00:00"),
                "open": 3080.0,
                "high": 3090.0,
                "low": 3075.0,
                "close": 3088.0,
                "volume": 1000,
                "open_oi": 1800000,
                "close_oi": 1810000,
            },
            {
                "id": 2,
                "datetime": ns("2026-07-23 10:00:00"),
                "open": 3088.0,
                "high": 3095.0,
                "low": 3080.0,
                "close": 3092.0,
                "volume": 500,
                "open_oi": 1810000,
                "close_oi": 1815000,
            },
        ]
    )
    api = FakeTqApi(
        frame,
        datetime(2026, 7, 23, 10, 5, tzinfo=SHANGHAI),
    )
    provider = TqSdkMarketDataProvider(
        "free-user",
        "free-password",
        api_factory=lambda: api,
        clock=lambda: api.now,
    )

    result = provider.fetch(
        MarketDataRequest(
            contract="RB2610",
            timeframe="60m",
            image_role="EXECUTION_60M",
        )
    )

    assert result is not None
    assert api.requested_duration == 3600
    assert result.bars[-2].is_closed is True
    assert result.bars[-1].is_closed is False
    assert result.last_bar_closed is False
