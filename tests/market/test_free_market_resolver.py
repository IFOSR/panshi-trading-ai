from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.market.bars import MarketBar
from trading_agent.market.providers.base import MarketDataRequest
from trading_agent.market.providers.composite import FreeMarketDataResolver
from trading_agent.market.resolver import (
    MarketDataFailure,
    MarketDataSnapshot,
    verify_and_merge_evidence,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def evidence(
    *,
    role: str = "STATE_DAILY",
    contract: str | None = None,
    timeframe: str | None = None,
) -> ScreenshotEvidence:
    return ScreenshotEvidence(
        image_role=role,
        contract=contract,
        timeframe=timeframe,
        provider="codex",
        model="gpt-5.6-sol",
        prompt_version="chart-evidence-v2",
        image_sha256="fixture",
    )


def snapshot(request: MarketDataRequest, source: str) -> MarketDataSnapshot:
    start = datetime(2026, 7, 1, 15, 0, tzinfo=SHANGHAI)
    bars = [
        MarketBar(
            contract=request.contract,
            timeframe=request.timeframe,
            timestamp=start + timedelta(days=index),
            trading_date=date(2026, 7, 1) + timedelta(days=index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=1000 + index,
            open_interest=5000 + index,
            is_closed=True,
            source=source,
        )
        for index in range(21)
    ]
    return MarketDataSnapshot(
        contract=request.contract,
        timeframe=request.timeframe,
        cutoff_time=bars[-1].timestamp,
        last_bar_closed=True,
        price_axis_verified=True,
        sources=[source],
        bars=bars,
    )


class RecordingProvider:
    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.requests: list[MarketDataRequest] = []

    def fetch(self, request: MarketDataRequest) -> MarketDataSnapshot:
        self.requests.append(request)
        if self.fail:
            raise RuntimeError(f"{self.name} unavailable")
        return snapshot(request, self.name)


class FlakyProvider:
    name = "akshare"

    def __init__(self) -> None:
        self.requests: list[MarketDataRequest] = []

    def fetch(self, request: MarketDataRequest) -> MarketDataSnapshot:
        self.requests.append(request)
        if len(self.requests) == 1:
            raise TimeoutError("temporary upstream timeout")
        return snapshot(request, self.name)


class FailingValidator:
    def validate(self, snapshot: MarketDataSnapshot) -> MarketDataSnapshot:
        raise ValueError("malformed official report")


def test_case_contract_wins_and_image_role_supplies_daily_timeframe() -> None:
    provider = RecordingProvider("tqsdk")
    resolver = FreeMarketDataResolver([provider])

    result = resolver.resolve(
        {"contract": "rb2610"},
        evidence(contract="rb2605"),
    )

    assert isinstance(result, MarketDataSnapshot)
    assert provider.requests[0].contract == "rb2610"
    assert provider.requests[0].timeframe == "1d"


def test_execution_role_supplies_60_minute_timeframe() -> None:
    provider = RecordingProvider("tqsdk")
    resolver = FreeMarketDataResolver([provider])

    resolver.resolve(
        {"contract": "rb2610"},
        evidence(role="EXECUTION_60M"),
    )

    assert provider.requests[0].timeframe == "60m"


def test_primary_failure_falls_back_and_records_quality_issue() -> None:
    primary = RecordingProvider("tqsdk", fail=True)
    fallback = RecordingProvider("akshare")
    resolver = FreeMarketDataResolver([primary, fallback])

    result = resolver.resolve(
        {"contract": "rb2610"},
        evidence(timeframe="1d"),
    )

    assert isinstance(result, MarketDataSnapshot)
    assert result.sources == ["akshare"]
    assert result.quality_issues == ["TQSDK_UNAVAILABLE"]
    assert len(primary.requests) == 1
    assert len(fallback.requests) == 1


def test_last_provider_retries_once_before_returning_a_blocker() -> None:
    provider = FlakyProvider()
    resolver = FreeMarketDataResolver([provider])

    result = resolver.resolve(
        {"contract": "rb2610"},
        evidence(timeframe="1d"),
    )

    assert isinstance(result, MarketDataSnapshot)
    assert len(provider.requests) == 2
    assert result.sources == ["akshare"]
    assert result.quality_issues == []


def test_all_provider_failures_become_auditable_market_data_blocker() -> None:
    resolver = FreeMarketDataResolver(
        [
            RecordingProvider("tqsdk", fail=True),
            RecordingProvider("akshare", fail=True),
        ]
    )

    resolution = resolver.resolve(
        {"contract": "rb2610"},
        evidence(timeframe="1d"),
    )
    assert isinstance(resolution, MarketDataFailure)

    merged = verify_and_merge_evidence(evidence(timeframe="1d"), resolution)

    assert "MARKET_DATA_UNAVAILABLE" in merged.blocking_issues
    assert merged.market_data_quality_issues == [
        "TQSDK_UNAVAILABLE",
        "AKSHARE_UNAVAILABLE",
    ]
    assert merged.allowed_usage.value == "QUALITATIVE_ONLY"


def test_validator_failure_does_not_discard_provider_data() -> None:
    resolver = FreeMarketDataResolver(
        [RecordingProvider("akshare")],
        validators=[FailingValidator()],
    )

    resolution = resolver.resolve(
        {"contract": "rb2610"},
        evidence(timeframe="1d"),
    )

    assert isinstance(resolution, MarketDataSnapshot)
    assert resolution.sources == ["akshare"]
    assert resolution.quality_issues == ["MARKET_DATA_VALIDATION_UNAVAILABLE"]
