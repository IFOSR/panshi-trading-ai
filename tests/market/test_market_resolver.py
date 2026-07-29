from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from trading_agent.market.bars import MarketBar
import httpx
import pytest
from pydantic import ValidationError

from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.market.providers.akshare import AkShareMarketDataProvider
from trading_agent.market.providers.composite import FreeMarketDataResolver
from trading_agent.market.providers.tqsdk import TqSdkMarketDataProvider
from trading_agent.market.providers.validation import AkShareExchangeDailyValidator
from trading_agent.market.resolver import (
    HttpMarketDataResolver,
    MarketDataSnapshot,
    configured_market_data_resolver,
    snapshot_to_verified_data,
    verify_and_merge_evidence,
)


def test_structured_bars_calculate_versioned_indicators_and_strategy_facts() -> None:
    start = datetime(2026, 6, 1, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    bars = [
        MarketBar(
            contract="rb2610",
            timeframe="1d",
            timestamp=start + timedelta(days=index),
            trading_date=date(2026, 6, 1) + timedelta(days=index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=1000 + index,
            open_interest=5000 + index * 10,
            settlement=101 + index,
            is_closed=True,
            source="fixture",
        )
        for index in range(30)
    ]

    verified = snapshot_to_verified_data(
        MarketDataSnapshot(
            contract="rb2610",
            timeframe="1d",
            cutoff_time=bars[-1].timestamp,
            last_bar_closed=True,
            price_axis_verified=True,
            bars=bars,
        )
    )

    assert verified["indicators"]["boll"]["formula_version"] == "boll-population-std-v1"
    assert verified["indicators"]["macd"]["formula_version"] == "macd-ema-seed-first-v1"
    assert verified["indicators"]["atr"]["formula_version"] == "atr-wilder-v1"
    assert verified["open_interest_change"] == 10
    assert verified["trend_score"] in {-3, -1, 1, 3}
    assert verified["strategy_facts"]["price_location"] != "UNKNOWN"


def test_snapshot_exposes_market_data_sources_and_validation_audit() -> None:
    start = datetime(2026, 7, 22, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    bars = [
        MarketBar(
            contract="rb2610",
            timeframe="1d",
            timestamp=start + timedelta(days=index),
            trading_date=date(2026, 7, 22) + timedelta(days=index),
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

    verified = snapshot_to_verified_data(
        MarketDataSnapshot(
            contract="rb2610",
            timeframe="1d",
            cutoff_time=bars[-1].timestamp,
            last_bar_closed=True,
            price_axis_verified=True,
            bars=bars,
            sources=["tqsdk"],
            validation_sources=["SHFE_OFFICIAL_DAILY"],
            quality_issues=["WAREHOUSE_DATA_UNAVAILABLE"],
        )
    )
    merged = verify_and_merge_evidence(
        ScreenshotEvidence(
            image_role="STATE_DAILY",
            provider="codex",
            model="gpt-5.6-sol",
            prompt_version="chart-evidence-v2",
            image_sha256="fixture",
        ),
        MarketDataSnapshot(
            contract="rb2610",
            timeframe="1d",
            cutoff_time=bars[-1].timestamp,
            last_bar_closed=True,
            price_axis_verified=True,
            bars=bars,
            sources=["tqsdk"],
            validation_sources=["SHFE_OFFICIAL_DAILY"],
            quality_issues=["WAREHOUSE_DATA_UNAVAILABLE"],
        ),
    )

    assert verified["market_data_sources"] == ["tqsdk"]
    assert verified["market_data_validation_sources"] == ["SHFE_OFFICIAL_DAILY"]
    assert verified["market_data_quality_issues"] == ["WAREHOUSE_DATA_UNAVAILABLE"]
    assert merged.market_data_sources == ["tqsdk"]
    assert merged.market_data_validation_sources == ["SHFE_OFFICIAL_DAILY"]
    assert merged.market_data_quality_issues == ["WAREHOUSE_DATA_UNAVAILABLE"]


def test_closed_60_minute_bars_generate_structured_price_confirmation() -> None:
    start = datetime(2026, 7, 22, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    bars = []
    for index in range(22):
        latest = index == 21
        bars.append(
            MarketBar(
                contract="rb2610",
                timeframe="60m",
                timestamp=start + timedelta(hours=index),
                trading_date=date(2026, 7, 22),
                open=100,
                high=112 if latest else 110,
                low=90,
                close=111 if latest else 105,
                volume=1000 + index,
                open_interest=5000 + index,
                is_closed=True,
                source="tqsdk",
            )
        )

    verified = snapshot_to_verified_data(
        MarketDataSnapshot(
            contract="rb2610",
            timeframe="60m",
            cutoff_time=bars[-1].timestamp,
            last_bar_closed=True,
            price_axis_verified=True,
            sources=["tqsdk"],
            bars=bars,
        )
    )

    assert verified["strategy_facts"]["price_confirmation"] is True
    assert (
        verified["strategy_facts"]["price_confirmation_direction"]
        == "BULLISH"
    )
    assert verified["strategy_facts"]["price_confirmation_type"] == "BREAKOUT"
    assert verified["indicators"]["price_confirmation"] == {
        "confirmed": True,
        "direction": "BULLISH",
        "kind": "BREAKOUT",
        "reference_price": 110,
        "formula_version": "price-confirmation-range-boll-v1",
    }


def test_twenty_one_closed_60_minute_bars_are_insufficient_for_confirmation() -> None:
    start = datetime(2026, 7, 22, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    bars = [
        MarketBar(
            contract="rb2610",
            timeframe="60m",
            timestamp=start + timedelta(hours=index),
            trading_date=date(2026, 7, 22),
            open=100,
            high=110,
            low=90,
            close=100,
            volume=1000 + index,
            open_interest=5000 + index,
            is_closed=True,
            source="fixture",
        )
        for index in range(21)
    ]

    verified = snapshot_to_verified_data(
        MarketDataSnapshot(
            contract="rb2610",
            timeframe="60m",
            cutoff_time=bars[-1].timestamp,
            last_bar_closed=True,
            price_axis_verified=True,
            rollover_active=False,
            near_price_limit=False,
            sources=["fixture"],
            bars=bars,
        )
    )

    assert verified["blocking_issues"] == ["MARKET_HISTORY_INSUFFICIENT"]
    assert verified["strategy_facts"]["price_confirmation"] is None
    assert verified["indicators"] == {}


def test_unclosed_60_minute_bar_is_excluded_from_structured_confirmation() -> None:
    start = datetime(2026, 7, 22, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    bars = [
        MarketBar(
            contract="rb2610",
            timeframe="60m",
            timestamp=start + timedelta(hours=index),
            trading_date=date(2026, 7, 22),
            open=100,
            high=110,
            low=90,
            close=100,
            volume=1000 + index,
            open_interest=5000 + index,
            is_closed=index < 22,
            source="fixture",
        )
        for index in range(23)
    ]
    bars[-1] = bars[-1].model_copy(
        update={
            "high": 130,
            "close": 125,
            "is_closed": False,
        }
    )

    verified = snapshot_to_verified_data(
        MarketDataSnapshot(
            contract="rb2610",
            timeframe="60m",
            cutoff_time=bars[-1].timestamp,
            last_bar_closed=False,
            price_axis_verified=True,
            rollover_active=False,
            near_price_limit=False,
            sources=["fixture"],
            bars=bars,
        )
    )

    assert verified["cutoff_time"] == bars[-2].timestamp.isoformat()
    assert verified["last_bar_closed"] is True
    assert verified["latest_close"] == bars[-2].close
    assert verified["strategy_facts"]["price_confirmation"] is False


def test_unclosed_60_minute_bar_with_too_little_closed_history_is_blocked() -> None:
    start = datetime(2026, 7, 22, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    bars = [
        MarketBar(
            contract="rb2610",
            timeframe="60m",
            timestamp=start + timedelta(hours=index),
            trading_date=date(2026, 7, 22),
            open=100,
            high=110,
            low=90,
            close=100,
            volume=1000 + index,
            open_interest=5000 + index,
            is_closed=index == 0,
            source="fixture",
        )
        for index in range(2)
    ]

    verified = snapshot_to_verified_data(
        MarketDataSnapshot(
            contract="rb2610",
            timeframe="60m",
            cutoff_time=bars[-1].timestamp,
            last_bar_closed=False,
            price_axis_verified=True,
            rollover_active=False,
            near_price_limit=False,
            sources=["fixture"],
            bars=bars,
        )
    )

    assert verified["blocking_issues"] == ["MARKET_HISTORY_INSUFFICIENT"]
    assert verified["strategy_facts"]["price_confirmation"] is None


def test_short_market_history_returns_a_blocker_instead_of_raising() -> None:
    start = datetime(2026, 7, 20, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    bars = [
        MarketBar(
            contract="rb2610",
            timeframe="60m",
            timestamp=start + timedelta(hours=index),
            trading_date=date(2026, 7, 20),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=1000 + index,
            open_interest=5000 + index * 10,
            is_closed=True,
            source="fixture",
        )
        for index in range(2)
    ]

    verified = snapshot_to_verified_data(
            MarketDataSnapshot(
                contract="rb2610",
                timeframe="60m",
                cutoff_time=bars[-1].timestamp,
                last_bar_closed=True,
                price_axis_verified=True,
                rollover_active=False,
                near_price_limit=False,
                bars=bars,
            )
    )

    assert verified["blocking_issues"] == ["MARKET_HISTORY_INSUFFICIENT"]
    assert verified["strategy_facts"]["trend_bias"] == "UNKNOWN"
    assert verified["strategy_facts"]["price_location"] == "UNKNOWN"
    assert "boll" not in verified["indicators"]
    assert "atr" not in verified["indicators"]

    merged = verify_and_merge_evidence(
        ScreenshotEvidence(
            image_role="EXECUTION_60M",
            contract="rb2610",
            timeframe="60m",
            provider="codex",
            model="gpt-5.6-sol",
            prompt_version="chart-evidence-v2",
            image_sha256="fixture",
        ),
        MarketDataSnapshot(
            contract="rb2610",
            timeframe="60m",
            cutoff_time=bars[-1].timestamp,
            last_bar_closed=True,
            price_axis_verified=True,
            bars=bars,
        ),
    )

    assert "MARKET_HISTORY_INSUFFICIENT" in merged.blocking_issues


def test_twenty_bars_are_insufficient_for_current_vs_prior_twenty_trend() -> None:
    start = datetime(2026, 6, 1, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    bars = [
        MarketBar(
            contract="rb2610",
            timeframe="1d",
            timestamp=start + timedelta(days=index),
            trading_date=date(2026, 6, 1) + timedelta(days=index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=1000 + index,
            open_interest=5000 + index,
            is_closed=True,
            source="fixture",
        )
        for index in range(20)
    ]

    verified = snapshot_to_verified_data(
            MarketDataSnapshot(
                contract="rb2610",
                timeframe="1d",
                cutoff_time=bars[-1].timestamp,
                last_bar_closed=True,
                rollover_active=False,
                near_price_limit=False,
                bars=bars,
            )
    )

    assert verified["blocking_issues"] == ["MARKET_HISTORY_INSUFFICIENT"]


def test_http_market_data_resolver_returns_verified_snapshot() -> None:
    payload = {
        "contract": "rb2610",
        "timeframe": "1d",
        "cutoff_time": "2026-07-20T15:00:00+08:00",
        "last_bar_closed": True,
        "price_axis_verified": True,
        "rollover_active": False,
        "near_price_limit": False,
        "bars": [
            {
                "contract": "rb2610",
                "timeframe": "1d",
                "timestamp": "2026-07-19T15:00:00+08:00",
                "trading_date": "2026-07-19",
                "open": 100,
                "high": 102,
                "low": 99,
                "close": 101,
                "volume": 1000,
                "open_interest": 5000,
                "settlement": 101,
                "is_closed": True,
                "source": "fixture",
            },
            {
                "contract": "rb2610",
                "timeframe": "1d",
                "timestamp": "2026-07-20T15:00:00+08:00",
                "trading_date": "2026-07-20",
                "open": 101,
                "high": 103,
                "low": 100,
                "close": 102,
                "volume": 1100,
                "open_interest": 5100,
                "settlement": 102,
                "is_closed": True,
                "source": "fixture",
            },
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/resolve"
        return httpx.Response(200, json=payload)

    resolver = HttpMarketDataResolver(
        "http://market-data",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    snapshot = resolver.resolve(
        {"contract": "rb2610"},
        ScreenshotEvidence(
            image_role="STATE_DAILY",
            contract="rb2610",
            timeframe="1d",
            provider="codex",
            model="gpt-5.6-sol",
            prompt_version="chart-evidence-v2",
            image_sha256="fixture",
        ),
    )

    assert snapshot is not None
    assert snapshot.contract == "rb2610"
    assert snapshot.bars[-1].close == 102


def test_worker_market_data_resolver_is_built_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("TRADING_AGENT_MARKET_DATA_URL", "http://market-data")

    resolver = configured_market_data_resolver()

    assert isinstance(resolver, HttpMarketDataResolver)


def test_free_market_data_resolver_uses_akshare_without_tq_credentials(
    monkeypatch,
) -> None:
    monkeypatch.delenv("TRADING_AGENT_MARKET_DATA_URL", raising=False)
    monkeypatch.setenv("TRADING_AGENT_MARKET_DATA_PROVIDER", "free")
    monkeypatch.delenv("TRADING_AGENT_TQSDK_USERNAME", raising=False)
    monkeypatch.delenv("TRADING_AGENT_TQSDK_PASSWORD", raising=False)

    resolver = configured_market_data_resolver()

    assert isinstance(resolver, FreeMarketDataResolver)
    assert len(resolver.providers) == 1
    assert isinstance(resolver.providers[0], AkShareMarketDataProvider)
    assert len(resolver.validators) == 1
    assert isinstance(resolver.validators[0], AkShareExchangeDailyValidator)


def test_free_market_data_resolver_prefers_tqsdk_when_credentials_exist(
    monkeypatch,
) -> None:
    monkeypatch.delenv("TRADING_AGENT_MARKET_DATA_URL", raising=False)
    monkeypatch.setenv("TRADING_AGENT_MARKET_DATA_PROVIDER", "free")
    monkeypatch.setenv("TRADING_AGENT_TQSDK_USERNAME", "free-user")
    monkeypatch.setenv("TRADING_AGENT_TQSDK_PASSWORD", "free-password")

    resolver = configured_market_data_resolver()

    assert isinstance(resolver, FreeMarketDataResolver)
    assert isinstance(resolver.providers[0], TqSdkMarketDataProvider)
    assert isinstance(resolver.providers[1], AkShareMarketDataProvider)


def test_snapshot_rejects_mixed_contract_or_timeframe_bars() -> None:
    start = datetime(2026, 7, 20, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    bars = [
        MarketBar(
            contract="rb2610",
            timeframe="60m",
            timestamp=start,
            trading_date=date(2026, 7, 20),
            open=100,
            high=102,
            low=99,
            close=101,
            volume=1000,
            open_interest=5000,
            is_closed=True,
            source="fixture",
        ),
        MarketBar(
            contract="hc2610",
            timeframe="1d",
            timestamp=start + timedelta(hours=1),
            trading_date=date(2026, 7, 20),
            open=101,
            high=103,
            low=100,
            close=102,
            volume=1100,
            open_interest=5100,
            is_closed=True,
            source="fixture",
        ),
    ]

    with pytest.raises(ValidationError):
        MarketDataSnapshot(
            contract="rb2610",
            timeframe="60m",
            cutoff_time=start + timedelta(hours=1),
            last_bar_closed=True,
            bars=bars,
        )


def test_snapshot_rejects_bars_after_or_not_ending_at_cutoff() -> None:
    start = datetime(2026, 7, 20, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    bars = [
        MarketBar(
            contract="rb2610",
            timeframe="60m",
            timestamp=start,
            trading_date=date(2026, 7, 20),
            open=100,
            high=102,
            low=99,
            close=101,
            volume=1000,
            open_interest=5000,
            is_closed=True,
            source="fixture",
        ),
        MarketBar(
            contract="rb2610",
            timeframe="60m",
            timestamp=start + timedelta(hours=2),
            trading_date=date(2026, 7, 20),
            open=101,
            high=103,
            low=100,
            close=102,
            volume=1100,
            open_interest=5100,
            is_closed=True,
            source="fixture",
        ),
    ]

    with pytest.raises(ValidationError):
        MarketDataSnapshot(
            contract="rb2610",
            timeframe="60m",
            cutoff_time=start + timedelta(hours=1),
            last_bar_closed=True,
            bars=bars,
        )
