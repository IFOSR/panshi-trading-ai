"""TDD tests for EntitlementService."""

from datetime import datetime, timedelta, timezone

from trading_agent.db.base import Base, build_engine, session_factory
from trading_agent.db.models import UserRecord
from trading_agent.entitlement.service import EntitlementService
from trading_agent.entitlement.models import EntitlementResult


def make_sessions():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return session_factory(engine)


def _create_user(session, user_id="u1", username="trader"):
    user = UserRecord(user_id=user_id, username=username, password_hash="h")
    session.add(user)
    session.flush()
    return user


def test_check_access_returns_denied_for_no_entitlement() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
    with sessions() as session:
        svc = EntitlementService(session)
        result = svc.check_access("u1", "strategy_x", "1.0.0")
    assert result.accessible is False
    assert result.reason == "no_entitlement"


def test_grant_and_check_access() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
    with sessions() as session:
        with session.begin():
            svc = EntitlementService(session)
            ent = svc.grant_access(
                user_id="u1",
                strategy_id="trend_breakout",
                version="1.0.0",
                access_type="subscription",
                order_id="order-1",
            )
            assert ent.status == "active"
    with sessions() as session:
        svc = EntitlementService(session)
        result = svc.check_access("u1", "trend_breakout", "1.0.0")
    assert result.accessible is True
    assert result.access_type == "subscription"


def test_check_access_denies_expired_entitlement() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
    with sessions() as session:
        with session.begin():
            svc = EntitlementService(session)
            svc.grant_access(
                user_id="u1",
                strategy_id="trend_breakout",
                version="1.0.0",
                access_type="subscription",
                order_id="order-1",
                expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
    with sessions() as session:
        svc = EntitlementService(session)
        result = svc.check_access("u1", "trend_breakout")
    assert result.accessible is False
    assert result.reason == "expired"


def test_list_user_entitlements() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
            _create_user(session, "u2", "trader2")
    with sessions() as session:
        with session.begin():
            svc = EntitlementService(session)
            svc.grant_access("u1", "s1", "1.0.0", "free", None)
            svc.grant_access("u1", "s2", "1.0.0", "onetime", "o2")
    with sessions() as session:
        svc = EntitlementService(session)
        ents = svc.list_user_entitlements("u1")
        assert len(ents) == 2
        assert {e.strategy_id for e in ents} == {"s1", "s2"}


def test_expire_overdue_entitlements() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
    with sessions() as session:
        with session.begin():
            svc = EntitlementService(session)
            svc.grant_access(
                "u1", "expired_strategy", "1.0.0", "subscription", "o1",
                expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            )
            svc.grant_access(
                "u1", "active_strategy", "1.0.0", "subscription", "o2",
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
    with sessions() as session:
        with session.begin():
            svc = EntitlementService(session)
            count = svc.expire_overdue_entitlements()
            assert count == 1
    with sessions() as session:
        svc = EntitlementService(session)
        assert svc.check_access("u1", "active_strategy").accessible is True
        assert svc.check_access("u1", "expired_strategy").accessible is False
