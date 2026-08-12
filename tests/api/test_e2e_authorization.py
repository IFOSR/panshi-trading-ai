"""End-to-end integration test: registration → purchase → authorization → analysis.

Exercises the complete user journey defined in PRD v2.1.
"""

from fastapi.testclient import TestClient

from trading_agent.api.app import create_app
from trading_agent.auth.passwords import hash_password
from trading_agent.auth.repository import AuthRepository

API_HEADERS = {"Authorization": "Bearer private-api-token"}


def client() -> TestClient:
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        api_token="private-api-token",
    )
    with app.state.sessions() as session:
        with session.begin():
            AuthRepository(session).set_password(
                "trader_e2e",
                hash_password("test123"),
            )
    return TestClient(app)


def _login(c: TestClient, username="trader_e2e", password="test123") -> str:
    resp = c.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
        headers=API_HEADERS,
    )
    assert resp.status_code == 200
    return resp.json()["session_token"]


# ── Store E2E ──


def test_store_lists_strategies() -> None:
    c = client()
    resp = c.get("/v1/store/strategies", headers=API_HEADERS)
    assert resp.status_code == 200
    strategies = resp.json()
    assert any(
        s["strategy_id"] == "structure_confirmation" for s in strategies
    )


def test_store_strategy_detail() -> None:
    c = client()
    resp = c.get(
        "/v1/store/strategies/structure_confirmation",
        headers=API_HEADERS,
    )
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["strategy_id"] == "structure_confirmation"
    assert detail["display_name"] == "结构确认策略"
    assert detail["version"] == "1.0.0"


def test_store_strategy_404() -> None:
    c = client()
    resp = c.get("/v1/store/strategies/nonexistent", headers=API_HEADERS)
    assert resp.status_code == 404


# ── Purchase + Authorization E2E ──


def test_full_purchase_and_authorization_flow() -> None:
    c = client()
    session_id = _login(c)
    headers = {
        **API_HEADERS,
        "X-Panshi-Session": session_id,
    }

    # Check entitlement - initially none
    resp = c.get("/v1/entitlements", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 0

    # Create order
    resp = c.post(
        "/v1/orders",
        headers=headers,
        json={
            "strategy_id": "trend_breakout",
            "version": "1.0.0",
            "pricing_type": "subscription",
            "subscription_period": "monthly",
        },
    )
    assert resp.status_code == 200
    order = resp.json()
    assert order["status"] == "pending"
    order_id = order["order_id"]

    # Mark paid
    resp = c.post(f"/v1/orders/{order_id}/paid", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "paid"

    # Check entitlement now active
    resp = c.get("/v1/entitlements", headers=headers)
    assert resp.status_code == 200
    entitlements = resp.json()
    assert len(entitlements) == 1
    assert entitlements[0]["strategy_id"] == "trend_breakout"

    # Check specific strategy access
    resp = c.get(
        "/v1/entitlements/trend_breakout/check?version=1.0.0",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["accessible"] is True


def test_check_access_denied_for_unpurchased_strategy() -> None:
    c = client()
    session_id = _login(c)

    resp = c.get(
        "/v1/entitlements/premium_strategy/check",
        headers={
            **API_HEADERS,
            "X-Panshi-Session": session_id,
        },
    )
    assert resp.status_code == 200
    result = resp.json()
    assert result["accessible"] is False
    assert result["reason"] == "no_entitlement"
