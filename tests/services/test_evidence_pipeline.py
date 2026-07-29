from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.market.bars import MarketBar
from trading_agent.market.resolver import MarketDataSnapshot
from trading_agent.services.evidence_pipeline import merge_case_market_data


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _snapshot(role: str, timeframe: str) -> MarketDataSnapshot:
    start = datetime(2026, 7, 20, 15, 0, tzinfo=SHANGHAI)
    bars = [
        MarketBar(
            contract="rb2610",
            timeframe=timeframe,
            timestamp=start + timedelta(hours=index),
            trading_date=date(2026, 7, 20),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=1000 + index,
            open_interest=5000 + index,
            is_closed=True,
            source="fixture",
        )
        for index in range(22)
    ]
    return MarketDataSnapshot(
        contract="rb2610",
        timeframe=timeframe,
        cutoff_time=bars[-1].timestamp,
        last_bar_closed=True,
        price_axis_verified=True,
        rollover_active=False,
        near_price_limit=False,
        sources=["fixture"],
        bars=bars,
    )


class RecordingResolver:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str | None, str | None]] = []

    def resolve(self, case_state, evidence):
        self.requests.append(
            (evidence.image_role, evidence.timeframe, evidence.contract)
        )
        timeframe = "60m" if evidence.image_role == "EXECUTION_60M" else "1d"
        return _snapshot(evidence.image_role, timeframe)


def test_daily_only_image_gets_an_automatic_execution_market_evidence() -> None:
    resolver = RecordingResolver()
    daily = ScreenshotEvidence(
        image_role="STATE_DAILY",
        contract="rb2610",
        timeframe="1d",
        provider="codex",
        model="gpt-5.6-sol",
        prompt_version="chart-evidence-v2",
        image_sha256="daily",
    )

    result = merge_case_market_data(
        case_state={"contract": "rb2610"},
        evidence_set=[daily],
        market_data_resolver=resolver,
    )

    assert [item.image_role for item in result] == [
        "STATE_DAILY",
        "EXECUTION_60M",
    ]
    assert resolver.requests == [
        ("STATE_DAILY", "1d", "rb2610"),
        ("EXECUTION_60M", "60m", "rb2610"),
    ]
    assert result[1].provider == "structured-market-data"
    assert result[1].timeframe == "60m"


def test_synthetic_execution_inherits_contract_extracted_from_daily_image() -> None:
    resolver = RecordingResolver()
    daily = ScreenshotEvidence(
        image_role="STATE_DAILY",
        contract="rb2610",
        timeframe="1d",
        provider="codex",
        model="gpt-5.6-sol",
        prompt_version="chart-evidence-v2",
        image_sha256="daily",
    )

    merge_case_market_data(
        case_state={},
        evidence_set=[daily],
        market_data_resolver=resolver,
    )

    assert resolver.requests[-1] == ("EXECUTION_60M", "60m", "rb2610")


def test_blocked_execution_image_is_replaced_by_structured_market_evidence() -> None:
    resolver = RecordingResolver()
    daily = ScreenshotEvidence(
        image_role="STATE_DAILY",
        contract="rb2610",
        timeframe="1d",
        provider="codex",
        model="gpt-5.6-sol",
        prompt_version="chart-evidence-v2",
        image_sha256="daily",
    )
    blocked_execution = ScreenshotEvidence(
        image_role="EXECUTION_60M",
        contract="cu2609",
        timeframe="60m",
        provider="privacy-gate",
        model="none",
        prompt_version="privacy-policy-v1",
        image_sha256="execution",
        allowed_usage="BLOCKED",
        blocking_issues=["PRIVACY_REVIEW_REQUIRED"],
    )

    result = merge_case_market_data(
        case_state={},
        evidence_set=[daily, blocked_execution],
        market_data_resolver=resolver,
    )

    execution = [
        item for item in result if item.image_role == "EXECUTION_60M"
    ]
    assert len(execution) == 1
    assert execution[0].provider == "structured-market-data"
    assert execution[0].allowed_usage == "EXACT"
    assert resolver.requests[-1] == ("EXECUTION_60M", "60m", "rb2610")


def test_identity_conflict_is_not_erased_by_synthetic_role_replacement() -> None:
    resolver = RecordingResolver()
    daily = ScreenshotEvidence(
        image_role="STATE_DAILY",
        contract="rb2610",
        timeframe="1d",
        cutoff_time="2026-07-22T15:00:00+08:00",
        provider="codex",
        model="gpt-5.6-sol",
        prompt_version="chart-evidence-v2",
        image_sha256="daily",
    )

    result = merge_case_market_data(
        case_state={"contract": "rb2610"},
        evidence_set=[daily],
        market_data_resolver=resolver,
    )

    state_items = [
        item for item in result if item.image_role == "STATE_DAILY"
    ]
    assert len(state_items) == 1
    assert state_items[0].provider == "codex"
    assert state_items[0].allowed_usage == "BLOCKED"
    assert "CUTOFF_CONFLICT" in state_items[0].blocking_issues


def test_synthetic_execution_inherits_contract_from_cutoff_blocked_daily() -> None:
    resolver = RecordingResolver()
    daily = ScreenshotEvidence(
        image_role="STATE_DAILY",
        contract="rb2610",
        timeframe="1d",
        cutoff_time="2026-07-22T15:00:00+08:00",
        provider="codex",
        model="gpt-5.6-sol",
        prompt_version="chart-evidence-v2",
        image_sha256="daily",
    )

    merge_case_market_data(
        case_state={},
        evidence_set=[daily],
        market_data_resolver=resolver,
    )

    assert resolver.requests[-1] == ("EXECUTION_60M", "60m", "rb2610")


def test_synthetic_execution_does_not_inherit_conflicting_contract() -> None:
    resolver = RecordingResolver()
    daily = ScreenshotEvidence(
        image_role="STATE_DAILY",
        contract="rb2610",
        timeframe="1d",
        provider="codex",
        model="gpt-5.6-sol",
        prompt_version="chart-evidence-v2",
        image_sha256="daily",
        allowed_usage="BLOCKED",
        blocking_issues=["CONTRACT_CONFLICT"],
    )

    merge_case_market_data(
        case_state={},
        evidence_set=[daily],
        market_data_resolver=resolver,
    )

    assert resolver.requests[-1] == ("EXECUTION_60M", "60m", None)
