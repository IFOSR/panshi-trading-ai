"""TDD tests for PerformanceTracker."""

from datetime import date, timedelta

from trading_agent.db.base import Base, build_engine, session_factory
from trading_agent.performance.tracker import PerformanceTracker
from trading_agent.strategies.contracts import (
    FactRequirement,
    DataRequirement,
    PerformanceTrack,
    StrategyInputSnapshot,
    StrategyManifest,
    StrategyRun,
)


class MockStrategy:
    manifest = StrategyManifest(
        strategy_id="mock_strategy",
        display_name="Mock Strategy",
        version="1.0.0",
        status="stable",
        entrypoint="test:MockStrategy",
        supported_markets=["CN_FUTURES"],
        risk_profile_id="mock-risk-v1",
        process_label="mock",
    )

    def evaluate(self, snapshot: StrategyInputSnapshot) -> StrategyRun:
        raise NotImplementedError

    def required_facts(self, context: dict) -> list[FactRequirement]:
        return []

    def required_data(self, context: dict) -> list[DataRequirement]:
        return []

    def track_performance(
        self,
        start_date: date,
        end_date: date,
        market_data: dict | None = None,
    ) -> PerformanceTrack:
        return PerformanceTrack(
            strategy_id="mock_strategy",
            version="1.0.0",
            start_date=start_date,
            end_date=end_date,
            signals=[
                {
                    "contract": "RB2610",
                    "signal_date": start_date,
                    "direction": "LONG",
                    "entry_price": 3500.0,
                    "exit_price": 3600.0,
                    "return_pct": 0.028,
                    "status": "closed",
                    "closed_date": end_date,
                },
                {
                    "contract": "RB2610",
                    "signal_date": start_date + timedelta(days=5),
                    "direction": "SHORT",
                    "entry_price": 3600.0,
                    "exit_price": 3580.0,
                    "return_pct": -0.005,
                    "status": "closed",
                    "closed_date": end_date,
                },
            ],
            summary={
                "total_return": 0.023,
                "signal_count": 2,
                "win_count": 1,
                "loss_count": 1,
                "win_rate": 0.5,
                "max_drawdown": 0.005,
                "equity_curve": [0, 0.028, 0.023],
            },
        )


def make_sessions():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return session_factory(engine)


def test_track_strategy_saves_signals() -> None:
    sessions = make_sessions()
    strategy = MockStrategy()
    start = date(2025, 5, 12)
    end = date(2025, 8, 12)

    with sessions() as session:
        with session.begin():
            tracker = PerformanceTracker(session)
            result = tracker.track_strategy(strategy, start, end)

    assert result.strategy_id == "mock_strategy"
    assert result.signal_count == 2
    assert result.total_return == 0.023
    assert result.win_rate == 0.5
    assert len(result.signals) == 2

    with sessions() as session:
        from trading_agent.performance.repository import PerformanceRepository
        repo = PerformanceRepository(session)
        signals = repo.list_signals("mock_strategy", "1.0.0")
        assert len(signals) == 2


def test_get_summary_returns_cached_data() -> None:
    sessions = make_sessions()
    strategy = MockStrategy()
    start = date(2025, 5, 12)
    end = date(2025, 8, 12)

    with sessions() as session:
        with session.begin():
            tracker = PerformanceTracker(session)
            tracker.track_strategy(strategy, start, end)

    with sessions() as session:
        tracker = PerformanceTracker(session)
        summary = tracker.get_summary("mock_strategy", "1.0.0")
        assert summary is not None
        assert summary.signal_count == 2


def test_get_summary_returns_none_for_unknown_strategy() -> None:
    sessions = make_sessions()
    with sessions() as session:
        tracker = PerformanceTracker(session)
        assert tracker.get_summary("unknown", "1.0.0") is None


def test_track_strategy_updates_existing_summary() -> None:
    sessions = make_sessions()
    strategy = MockStrategy()
    start = date(2025, 5, 12)
    end = date(2025, 8, 12)

    with sessions() as session:
        with session.begin():
            tracker = PerformanceTracker(session)
            tracker.track_strategy(strategy, start, end)

    strategy.manifest = StrategyManifest(
        strategy_id="mock_strategy",
        display_name="Mock Strategy",
        version="2.0.0",
        status="stable",
        entrypoint="test:MockStrategy",
        supported_markets=["CN_FUTURES"],
        risk_profile_id="mock-risk-v1",
        process_label="mock",
    )

    with sessions() as session:
        with session.begin():
            tracker = PerformanceTracker(session)
            tracker.track_strategy(strategy, start, end)

    with sessions() as session:
        tracker = PerformanceTracker(session)
        old = tracker.get_summary("mock_strategy", "1.0.0")
        new = tracker.get_summary("mock_strategy", "2.0.0")
        assert old is not None
        assert new is not None
        assert old.version == "1.0.0"
        assert new.version == "2.0.0"
