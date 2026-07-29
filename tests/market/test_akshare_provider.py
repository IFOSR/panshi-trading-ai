from datetime import date, datetime
import time
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from trading_agent.market.providers.akshare import AkShareMarketDataProvider
from trading_agent.market.providers.base import MarketDataRequest
from trading_agent.market.resolver import snapshot_to_verified_data


SHANGHAI = ZoneInfo("Asia/Shanghai")


class FakeAkShare:
    def __init__(
        self,
        *,
        daily: pd.DataFrame | None = None,
        minute: pd.DataFrame | None = None,
        realtime: pd.DataFrame | None = None,
    ) -> None:
        self.daily = daily
        self.minute = minute
        self.realtime = realtime

    def futures_zh_daily_sina(self, symbol):
        assert symbol == "RB2610"
        return self.daily

    def futures_zh_minute_sina(self, symbol, period):
        assert symbol == "RB2610"
        assert period == "60"
        return self.minute

    def futures_contract_detail(self, symbol):
        assert symbol == "RB2610"
        return pd.DataFrame(
            [
                {"item": "交易品种", "value": "螺纹钢"},
                {"item": "最小变动价位", "value": "1元/吨"},
                {"item": "交易单位", "value": "10吨/手"},
                {"item": "上市交易所", "value": "上海期货交易所"},
                {"item": "涨跌停板幅度", "value": "上一交易日结算价的±11%"},
                {
                    "item": "交易时间",
                    "value": "09:00-10:15 10:30-11:30 13:30-15:00 21:00-23:00",
                },
            ]
        )

    def tool_trade_date_hist_sina(self):
        return pd.DataFrame(
            {
                "trade_date": pd.to_datetime(
                    ["2026-07-22", "2026-07-23", "2026-07-24"]
                )
            }
        )

    def futures_zh_realtime(self, symbol):
        assert symbol == "螺纹钢"
        if self.realtime is not None:
            return self.realtime
        return pd.DataFrame(
            [
                {
                    "symbol": "RB0",
                    "trade": 3085.0,
                    "settlement": 3090.0,
                    "presettlement": 3083.0,
                    "volume": 833566,
                    "position": 1872417,
                },
                {
                    "symbol": "RB2610",
                    "trade": 3085.0,
                    "settlement": 3090.0,
                    "presettlement": 3083.0,
                    "volume": 833566,
                    "position": 1872417,
                },
            ]
        )


def test_akshare_normalizes_daily_settlement_and_contract_details() -> None:
    module = FakeAkShare(
        daily=pd.DataFrame(
            [
                {
                    "date": date(2026, 7, 22),
                    "open": 3070.0,
                    "high": 3090.0,
                    "low": 3060.0,
                    "close": 3083.0,
                    "volume": 1000,
                    "hold": 1810000,
                    "settle": 3083.0,
                },
                {
                    "date": date(2026, 7, 23),
                    "open": 3083.0,
                    "high": 3108.0,
                    "low": 3078.0,
                    "close": 3085.0,
                    "volume": 1200,
                    "hold": 1872417,
                    "settle": 3090.0,
                },
            ]
        )
    )
    provider = AkShareMarketDataProvider(
        module=module,
        clock=lambda: datetime(2026, 7, 23, 16, 0, tzinfo=SHANGHAI),
    )

    result = provider.fetch(
        MarketDataRequest(
            contract="rb2610",
            timeframe="1d",
            image_role="STATE_DAILY",
        )
    )

    assert result is not None
    assert result.last_bar_closed is True
    assert result.bars[-1].trading_date == date(2026, 7, 23)
    assert result.bars[-1].open_interest == 1872417
    assert result.bars[-1].settlement == 3090.0
    assert result.contract_metadata["exchange"] == "SHFE"
    assert result.contract_metadata["price_tick"] == 1.0
    assert result.contract_metadata["multiplier"] == 10.0
    assert result.contract_metadata["limit_rule"] == "上一交易日结算价的±11%"
    assert result.rollover_active is False
    assert result.near_price_limit is False
    assert result.sources == ["akshare"]


def test_akshare_assigns_night_bar_to_next_trading_date() -> None:
    module = FakeAkShare(
        minute=pd.DataFrame(
            [
                {
                    "datetime": "2026-07-22 22:00:00",
                    "open": 3070.0,
                    "high": 3090.0,
                    "low": 3060.0,
                    "close": 3083.0,
                    "volume": 1000,
                    "hold": 1810000,
                },
                {
                    "datetime": "2026-07-23 10:00:00",
                    "open": 3083.0,
                    "high": 3108.0,
                    "low": 3078.0,
                    "close": 3085.0,
                    "volume": 1200,
                    "hold": 1872417,
                },
            ]
        )
    )
    provider = AkShareMarketDataProvider(
        module=module,
        clock=lambda: datetime(2026, 7, 23, 10, 5, tzinfo=SHANGHAI),
    )

    result = provider.fetch(
        MarketDataRequest(
            contract="rb2610",
            timeframe="60m",
            image_role="EXECUTION_60M",
        )
    )

    assert result is not None
    assert result.bars[0].trading_date == date(2026, 7, 23)
    assert result.bars[-1].is_closed is True
    assert result.last_bar_closed is True


def test_akshare_rejects_changed_or_incomplete_upstream_schema() -> None:
    module = FakeAkShare(
        minute=pd.DataFrame(
            [{"datetime": "2026-07-23 10:00:00", "price": 3085.0}]
        )
    )
    provider = AkShareMarketDataProvider(module=module)

    with pytest.raises(ValueError, match="missing required columns"):
        provider.fetch(
            MarketDataRequest(
                contract="rb2610",
                timeframe="60m",
                image_role="EXECUTION_60M",
            )
        )


def test_akshare_bounds_slow_network_calls() -> None:
    class SlowAkShare(FakeAkShare):
        def futures_zh_daily_sina(self, symbol):
            time.sleep(0.2)
            return super().futures_zh_daily_sina(symbol)

    provider = AkShareMarketDataProvider(
        module=SlowAkShare(daily=pd.DataFrame()),
        timeout_seconds=0.01,
    )

    with pytest.raises(TimeoutError, match="AkShare market data timed out"):
        provider.fetch(
            MarketDataRequest(
                contract="rb2610",
                timeframe="1d",
                image_role="STATE_DAILY",
            )
        )


def test_akshare_marks_unknown_risk_flags_as_blocking() -> None:
    class MissingRealtimeAkShare(FakeAkShare):
        def futures_zh_realtime(self, symbol):
            raise RuntimeError("realtime table unavailable")

    provider = AkShareMarketDataProvider(
        module=MissingRealtimeAkShare(
            daily=pd.DataFrame(
                [
                    {
                        "date": date(2026, 7, 22),
                        "open": 3070.0,
                        "high": 3090.0,
                        "low": 3060.0,
                        "close": 3083.0,
                        "volume": 1000,
                        "hold": 1810000,
                        "settle": 3083.0,
                    },
                    {
                        "date": date(2026, 7, 23),
                        "open": 3083.0,
                        "high": 3108.0,
                        "low": 3078.0,
                        "close": 3085.0,
                        "volume": 1200,
                        "hold": 1872417,
                        "settle": 3090.0,
                    },
                ]
            )
        ),
    )

    result = provider.fetch(
        MarketDataRequest(
            contract="rb2610",
            timeframe="1d",
            image_role="STATE_DAILY",
        )
    )

    assert result is not None
    assert result.rollover_active is None
    assert result.near_price_limit is None
    verified = snapshot_to_verified_data(result)
    assert "ROLLOVER_STATUS_UNKNOWN" in verified["blocking_issues"]
    assert "PRICE_LIMIT_STATUS_UNKNOWN" in verified["blocking_issues"]
