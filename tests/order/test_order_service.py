"""TDD tests for OrderService."""

from trading_agent.db.base import Base, build_engine, session_factory
from trading_agent.db.models import UserRecord
from trading_agent.order.service import OrderService
from trading_agent.order.models import OrderCreateRequest
from trading_agent.entitlement.service import EntitlementService


def make_sessions():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return session_factory(engine)


def _create_user(session, user_id="u1", username="trader"):
    user = UserRecord(user_id=user_id, username=username, password_hash="h")
    session.add(user)
    session.flush()
    return user


def test_create_order_returns_pending() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
    with sessions() as session:
        with session.begin():
            svc = OrderService(session)
            order = svc.create_order("u1", OrderCreateRequest(
                strategy_id="trend_breakout",
                version="1.0.0",
                pricing_type="subscription",
                subscription_period="monthly",
            ))
    assert order.status == "pending"
    assert order.amount == 9900
    assert order.strategy_id == "trend_breakout"


def test_mark_paid_creates_entitlement() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
    with sessions() as session:
        with session.begin():
            svc = OrderService(session)
            order = svc.create_order("u1", OrderCreateRequest(
                strategy_id="trend_breakout",
                version="1.0.0",
                pricing_type="onetime",
            ))
            paid = svc.mark_paid(order.order_id)
    assert paid.status == "paid"
    assert paid.paid_at is not None

    with sessions() as session:
        ent_svc = EntitlementService(session)
        result = ent_svc.check_access("u1", "trend_breakout", "1.0.0")
    assert result.accessible is True


def test_refund_order() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
    with sessions() as session:
        with session.begin():
            svc = OrderService(session)
            order = svc.create_order("u1", OrderCreateRequest(
                strategy_id="s1",
                version="1.0.0",
                pricing_type="onetime",
            ))
            refunded = svc.refund(order.order_id, "用户申请退款")
    assert refunded.status == "refunded"
    assert refunded.refund_reason == "用户申请退款"


def test_list_orders_returns_user_orders() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            _create_user(session)
            _create_user(session, "u2", "other")
    with sessions() as session:
        with session.begin():
            svc = OrderService(session)
            svc.create_order("u1", OrderCreateRequest(
                strategy_id="s1", version="1.0.0", pricing_type="onetime",
            ))
            svc.create_order("u1", OrderCreateRequest(
                strategy_id="s2", version="1.0.0", pricing_type="free",
            ))
            svc.create_order("u2", OrderCreateRequest(
                strategy_id="s3", version="1.0.0", pricing_type="onetime",
            ))
    with sessions() as session:
        svc = OrderService(session)
        orders = svc.list_orders("u1")
        assert len(orders) == 2
        assert all(o.user_id == "u1" for o in orders)
