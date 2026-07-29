from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from trading_agent.api.app import create_app
from trading_agent.auth.passwords import hash_password
from trading_agent.auth.repository import AuthRepository
from trading_agent.auth.tokens import digest_session_token
from trading_agent.db.models import AuthSessionRecord


API_HEADERS = {"Authorization": "Bearer private-api-token"}


def make_client() -> TestClient:
    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        api_token="private-api-token",
    )
    with app.state.sessions() as session:
        with session.begin():
            AuthRepository(session).set_password(
                "ylfego",
                hash_password("correct-password"),
            )
    return TestClient(app)


def login(client: TestClient) -> str:
    response = client.post(
        "/v1/auth/login",
        headers=API_HEADERS,
        json={"username": "ylfego", "password": "correct-password"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["username"] == "ylfego"
    assert "password_hash" not in payload
    assert "token_hash" not in payload
    assert payload["session_token"]
    return payload["session_token"]


def test_valid_login_returns_raw_session_token_once_and_validates_it() -> None:
    client = make_client()

    token = login(client)
    response = client.get(
        "/v1/auth/session",
        headers={**API_HEADERS, "X-Panshi-Session": token},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "ylfego"
    with client.app.state.sessions() as session:
        stored = session.scalar(select(AuthSessionRecord))
    assert stored is not None
    assert stored.token_hash != token


def test_invalid_username_and_password_have_identical_responses() -> None:
    client = make_client()

    unknown = client.post(
        "/v1/auth/login",
        headers=API_HEADERS,
        json={"username": "missing", "password": "correct-password"},
    )
    wrong_password = client.post(
        "/v1/auth/login",
        headers=API_HEADERS,
        json={"username": "ylfego", "password": "wrong-password"},
    )

    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json() == wrong_password.json() == {
        "detail": "invalid username or password"
    }


def test_expired_malformed_and_disabled_sessions_are_rejected() -> None:
    client = make_client()
    expired_token = login(client)
    disabled_token = login(client)

    with client.app.state.sessions() as session:
        with session.begin():
            stored = session.scalar(
                select(AuthSessionRecord).where(
                    AuthSessionRecord.token_hash
                    == digest_session_token(expired_token)
                )
            )
            assert stored is not None
            stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    expired = client.get(
        "/v1/auth/session",
        headers={**API_HEADERS, "X-Panshi-Session": expired_token},
    )
    malformed = client.get(
        "/v1/auth/session",
        headers={**API_HEADERS, "X-Panshi-Session": "not-a-valid-session"},
    )

    with client.app.state.sessions() as session:
        with session.begin():
            AuthRepository(session).set_active("ylfego", False)
    disabled = client.get(
        "/v1/auth/session",
        headers={**API_HEADERS, "X-Panshi-Session": disabled_token},
    )

    assert expired.status_code == malformed.status_code == disabled.status_code == 401


def test_logout_is_idempotent_and_invalidates_the_session() -> None:
    client = make_client()
    token = login(client)
    headers = {**API_HEADERS, "X-Panshi-Session": token}

    first = client.post("/v1/auth/logout", headers=headers)
    repeated = client.post("/v1/auth/logout", headers=headers)
    validation = client.get("/v1/auth/session", headers=headers)

    assert first.status_code == repeated.status_code == 200
    assert first.json() == repeated.json() == {"ok": True}
    assert validation.status_code == 401


def test_auth_endpoints_require_private_api_bearer_token() -> None:
    client = make_client()

    login_response = client.post(
        "/v1/auth/login",
        json={"username": "ylfego", "password": "correct-password"},
    )
    session_response = client.get(
        "/v1/auth/session",
        headers={"X-Panshi-Session": "session-token"},
    )
    logout_response = client.post(
        "/v1/auth/logout",
        headers={"X-Panshi-Session": "session-token"},
    )

    assert login_response.status_code == 401
    assert session_response.status_code == 401
    assert logout_response.status_code == 401
