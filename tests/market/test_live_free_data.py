import os

import pytest

from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.market.resolver import (
    MarketDataSnapshot,
    configured_market_data_resolver,
)


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MARKET_DATA") != "1",
    reason="set RUN_LIVE_MARKET_DATA=1 to call free live data sources",
)


@pytest.mark.parametrize(
    ("role", "timeframe"),
    [
        ("STATE_DAILY", "1d"),
        ("EXECUTION_60M", "60m"),
    ],
)
def test_live_free_rb2610_market_data(role: str, timeframe: str) -> None:
    resolver = configured_market_data_resolver()
    resolution = resolver.resolve(
        {"contract": "rb2610"},
        ScreenshotEvidence(
            image_role=role,
            contract="rb2610",
            timeframe=timeframe,
            provider="live-smoke",
            model="none",
            prompt_version="live-smoke-v1",
            image_sha256="live-smoke",
        ),
    )

    assert isinstance(resolution, MarketDataSnapshot)
    assert len(resolution.bars) >= 21
    assert resolution.bars[-1].close > 0
    assert resolution.bars[-1].open_interest >= 0
    assert resolution.sources
