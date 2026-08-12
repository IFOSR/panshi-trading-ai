"""TDD tests for Phase 2: authorization database models (entitlements + orders)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from trading_agent.db.base import Base, build_engine, session_factory
from trading_agent.db.models import (
    UserEntitlementRecord,
    OrderRecord,
    UserRecord,
)


def make_sessions():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return session_factory(engine)


def _create_user(session, user_id: str = "user-001", username: str = "trader1") -> UserRecord:
    user = UserRecord(
        user_id=user_id,
        username=username,
        password_hash="hash",
    )
    session.add(user)
    session.flush()
    return user


# ── user_entitlements table ──


def test_user_entitlements_table_exists_and_has_expected_columns() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    columns = {
        col["name"]: col
        for col in inspector.get_columns("user_entitlements")
    }
    expected = {
        "entitlement_id", "user_id", "strategy_id", "version",
        "access_type", "status", "started_at", "expires_at",
        "order_id", "created_at", "updated_at",
    }
    assert expected.issubset(set(columns.keys()))


def test_insert_and_query_entitlement() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
            ent = UserEntitlementRecord(
                entitlement_id="ent-001",
                user_id="user-001",
                strategy_id="trend_breakout",
                version="1.0.0",
                access_type="subscription",
                status="active",
                order_id="order-001",
            )
            session.add(ent)

    with sessions() as session:
        result = session.get(UserEntitlementRecord, "ent-001")
        assert result is not None
        assert result.user_id == "user-001"
        assert result.strategy_id == "trend_breakout"
        assert result.access_type == "subscription"
        assert result.status == "active"


def test_entitlement_user_foreign_key() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            ent = UserEntitlementRecord(
                entitlement_id="ent-bad",
                user_id="nonexistent",
                strategy_id="s",
                version="1.0.0",
                access_type="free",
                status="active",
            )
            session.add(ent)
            with pytest.raises(IntegrityError):
                session.flush()


def test_entitlement_status_values() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
            ent = UserEntitlementRecord(
                entitlement_id="ent-active",
                user_id="user-001",
                strategy_id="s1",
                version="1.0.0",
                access_type="free",
                status="active",
            )
            session.add(ent)
            ent2 = UserEntitlementRecord(
                entitlement_id="ent-expired",
                user_id="user-001",
                strategy_id="s2",
                version="1.0.0",
                access_type="subscription",
                status="expired",
                expires_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            )
            session.add(ent2)

    with sessions() as session:
        active = session.get(UserEntitlementRecord, "ent-active")
        expired = session.get(UserEntitlementRecord, "ent-expired")
        assert active.status == "active"
        assert expired.status == "expired"


# ── orders table ──


def test_orders_table_exists_and_has_expected_columns() -> None:
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    columns = {
        col["name"]: col
        for col in inspector.get_columns("orders")
    }
    expected = {
        "order_id", "user_id", "strategy_id", "version",
        "pricing_type", "subscription_period", "amount", "currency",
        "status", "paid_at", "expires_at", "refund_reason",
        "created_at", "updated_at",
    }
    assert expected.issubset(set(columns.keys()))


def test_insert_and_query_order() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
            order = OrderRecord(
                order_id="order-001",
                user_id="user-001",
                strategy_id="trend_breakout",
                version="1.0.0",
                pricing_type="subscription",
                subscription_period="monthly",
                amount=9900,
                currency="CNY",
                status="pending",
            )
            session.add(order)

    with sessions() as session:
        result = session.get(OrderRecord, "order-001")
        assert result is not None
        assert result.user_id == "user-001"
        assert result.pricing_type == "subscription"
        assert result.amount == 9900


def test_order_user_foreign_key() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            order = OrderRecord(
                order_id="order-bad",
                user_id="nonexistent",
                strategy_id="s",
                version="1.0.0",
                pricing_type="onetime",
                amount=100,
                currency="CNY",
                status="pending",
            )
            session.add(order)
            with pytest.raises(IntegrityError):
                session.flush()


def test_order_lifecycle() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
            order = OrderRecord(
                order_id="lifecycle",
                user_id="user-001",
                strategy_id="s1",
                version="1.0.0",
                pricing_type="subscription",
                amount=9900,
                currency="CNY",
                status="pending",
            )
            session.add(order)

    # paid
    with sessions() as session:
        with session.begin():
            o = session.get(OrderRecord, "lifecycle")
            o.status = "paid"
            o.paid_at = datetime.now(timezone.utc)

    with sessions() as session:
        o = session.get(OrderRecord, "lifecycle")
        assert o.status == "paid"
        assert o.paid_at is not None

    # refunded
    with sessions() as session:
        with session.begin():
            o = session.get(OrderRecord, "lifecycle")
            o.status = "refunded"
            o.refund_reason = "用户申请"

    with sessions() as session:
        o = session.get(OrderRecord, "lifecycle")
        assert o.status == "refunded"
        assert o.refund_reason == "用户申请"
