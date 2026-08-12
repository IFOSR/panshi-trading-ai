"""TDD tests for Phase 1: new strategy store database models."""

from datetime import date

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from trading_agent.db.base import Base, build_engine, session_factory
from trading_agent.db.models import (
    PerformanceSignalRecord,
    PerformanceSummaryRecord,
    StrategyRecord,
    StrategyVersionRecord,
)


def make_sessions():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return session_factory(engine)


def test_strategies_table_exists_and_has_expected_columns() -> None:
    """策略表 (strategies) 存在且包含所有预期列。"""
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    columns = {
        column["name"]: column
        for column in inspector.get_columns("strategies")
    }
    expected = {
        "strategy_id", "display_name", "description", "category",
        "supported_markets", "supported_timeframes", "status",
        "entrypoint", "input_schema_version", "output_schema_version",
        "risk_profile_id", "process_label", "created_at", "updated_at",
    }
    assert expected.issubset(set(columns.keys()))


def test_strategy_versions_table_exists_and_has_expected_columns() -> None:
    """策略版本表 (strategy_versions) 存在且包含所有预期列。"""
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    columns = {
        column["name"]: column
        for column in inspector.get_columns("strategy_versions")
    }
    expected = {
        "version_id", "strategy_id", "version", "manifest",
        "pricing_type", "monthly_price", "yearly_price",
        "lifetime_price", "status", "released_at", "created_at",
    }
    assert expected.issubset(set(columns.keys()))


def test_can_insert_and_query_strategy() -> None:
    """可以插入并查询策略记录。"""
    sessions = make_sessions()
    record = StrategyRecord(
        strategy_id="trend_breakout",
        display_name="趋势突破策略",
        description="基于价格突破的信号分析",
        category="趋势",
        supported_markets=["CN_FUTURES"],
        supported_timeframes=["1d", "60m"],
        status="stable",
        entrypoint="test.module:TestStrategy",
    )

    with sessions() as session:
        with session.begin():
            session.add(record)

    with sessions() as session:
        result = session.get(StrategyRecord, "trend_breakout")
        assert result is not None
        assert result.display_name == "趋势突破策略"
        assert result.status == "stable"
        assert result.supported_markets == ["CN_FUTURES"]


def test_can_insert_and_query_strategy_version() -> None:
    """可以插入并查询策略版本记录，并与策略关联。"""
    sessions = make_sessions()
    strategy = StrategyRecord(
        strategy_id="trend_breakout",
        display_name="趋势突破策略",
        status="stable",
        entrypoint="test.module:TestStrategy",
        supported_markets=["CN_FUTURES"],
    )
    version = StrategyVersionRecord(
        version_id="trend_breakout@1.0.0",
        strategy_id="trend_breakout",
        version="1.0.0",
        manifest={"key": "value"},
        pricing_type="subscription",
        monthly_price=9900,
        yearly_price=89900,
        status="stable",
    )

    with sessions() as session:
        with session.begin():
            session.add(strategy)
            session.add(version)

    with sessions() as session:
        result = session.get(StrategyVersionRecord, "trend_breakout@1.0.0")
        assert result is not None
        assert result.pricing_type == "subscription"
        assert result.monthly_price == 9900
        assert result.strategy_id == "trend_breakout"


def test_can_insert_and_query_performance_signal() -> None:
    """可以插入并查询策略表现信号记录。"""
    sessions = make_sessions()
    record = PerformanceSignalRecord(
        signal_id="sig-001",
        strategy_id="trend_breakout",
        version="1.0.0",
        contract="RB2610",
        signal_date=date(2025, 6, 15),
        direction="LONG",
        entry_price=3550.0,
        exit_price=3600.0,
        return_pct=0.014,
        status="closed",
        closed_date=date(2025, 6, 20),
        evidence={"reason": "突破20日均线"},
    )

    with sessions() as session:
        with session.begin():
            session.add(record)

    with sessions() as session:
        result = session.get(PerformanceSignalRecord, "sig-001")
        assert result is not None
        assert result.direction == "LONG"
        assert result.return_pct == 0.014


def test_can_insert_and_query_performance_summary() -> None:
    """可以插入并查询策略表现汇总记录。"""
    sessions = make_sessions()
    record = PerformanceSummaryRecord(
        summary_id="trend_breakout@1.0.0@last_3_months",
        strategy_id="trend_breakout",
        version="1.0.0",
        period="last_3_months",
        start_date=date(2025, 5, 12),
        end_date=date(2025, 8, 12),
        total_return=0.125,
        max_drawdown=0.051,
        signal_count=24,
        win_count=15,
        loss_count=9,
        win_rate=0.625,
        equity_curve=[0, 0.05, 0.08, 0.125],
    )

    with sessions() as session:
        with session.begin():
            session.add(record)

    with sessions() as session:
        result = session.get(
            PerformanceSummaryRecord,
            "trend_breakout@1.0.0@last_3_months",
        )
        assert result is not None
        assert result.total_return == 0.125
        assert result.signal_count == 24
        assert result.win_rate == 0.625
        assert result.equity_curve == [0, 0.05, 0.08, 0.125]


def test_strategy_id_is_unique() -> None:
    """策略 ID 必须唯一。"""
    sessions = make_sessions()
    r1 = StrategyRecord(
        strategy_id="dup_id",
        display_name="策略A",
        status="stable",
        entrypoint="test.module:TestA",
        supported_markets=["CN_FUTURES"],
    )
    r2 = StrategyRecord(
        strategy_id="dup_id",
        display_name="策略B",
        status="stable",
        entrypoint="test.module:TestB",
        supported_markets=["CN_FUTURES"],
    )

    with sessions() as session:
        with session.begin():
            session.add(r1)
            with pytest.raises(IntegrityError):
                session.add(r2)
                session.flush()


def test_version_id_is_unique() -> None:
    """版本 ID 必须唯一。"""
    sessions = make_sessions()
    v1 = StrategyVersionRecord(
        version_id="dup@1.0.0",
        strategy_id="dup",
        version="1.0.0",
        manifest={},
        pricing_type="free",
        status="stable",
    )
    v2 = StrategyVersionRecord(
        version_id="dup@1.0.0",
        strategy_id="dup",
        version="1.0.0",
        manifest={},
        pricing_type="free",
        status="stable",
    )

    with sessions() as session:
        with session.begin():
            session.add(v1)
            with pytest.raises(IntegrityError):
                session.add(v2)
                session.flush()
