from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from trading_agent.auth.repository import AuthRepository
from trading_agent.db.base import Base, build_engine, session_factory
from trading_agent.db.models import AuthSessionRecord, UserRecord


def make_sessions():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return session_factory(engine)


def test_set_password_creates_normalized_user_and_replaces_hash() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = AuthRepository(session)
            created = repo.set_password("  YLFEGO  ", "hash-one")
            replaced = repo.set_password("ylfego", "hash-two")

    with sessions() as session:
        users = list(session.scalars(select(UserRecord)))

    assert created["user_id"] == replaced["user_id"]
    assert replaced["username"] == "ylfego"
    assert len(users) == 1
    assert users[0].password_hash == "hash-two"
    assert users[0].is_active is True


def test_set_password_rejects_empty_or_oversized_normalized_username() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = AuthRepository(session)
            with pytest.raises(ValueError, match="username"):
                repo.set_password("   ", "hash")
            with pytest.raises(ValueError, match="username"):
                repo.set_password("x" * 101, "hash")


def test_password_replacement_and_disable_revoke_existing_sessions() -> None:
    sessions = make_sessions()
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    with sessions() as session:
        with session.begin():
            repo = AuthRepository(session)
            repo.set_password("ylfego", "hash-one", now=now)
            repo.create_session(
                "ylfego",
                "a" * 64,
                expires_at=now + timedelta(hours=12),
                now=now,
            )
            repo.set_password("ylfego", "hash-two", now=now)
            assert repo.validate_session("a" * 64, now=now) is None
            repo.create_session(
                "ylfego",
                "b" * 64,
                expires_at=now + timedelta(hours=12),
                now=now,
            )
            assert repo.set_active("ylfego", False, now=now) is True
            assert repo.validate_session("b" * 64, now=now) is None
            assert repo.set_active("missing", False, now=now) is False


def test_session_validation_rejects_expired_and_inactive_users() -> None:
    sessions = make_sessions()
    now = datetime(2026, 7, 29, 8, tzinfo=timezone.utc)
    with sessions() as session:
        with session.begin():
            repo = AuthRepository(session)
            repo.set_password("ylfego", "hash", now=now)
            repo.create_session(
                "ylfego",
                "c" * 64,
                expires_at=now + timedelta(minutes=1),
                now=now,
            )
            current = repo.validate_session("c" * 64, now=now)
            expired = repo.validate_session(
                "c" * 64,
                now=now + timedelta(minutes=2),
            )

    assert current is not None
    assert current["username"] == "ylfego"
    assert expired is None


def test_revoke_and_expired_cleanup_are_idempotent() -> None:
    sessions = make_sessions()
    now = datetime(2026, 7, 29, 8, tzinfo=timezone.utc)
    with sessions() as session:
        with session.begin():
            repo = AuthRepository(session)
            repo.set_password("ylfego", "hash", now=now)
            repo.create_session(
                "ylfego",
                "d" * 64,
                expires_at=now - timedelta(seconds=1),
                now=now - timedelta(hours=1),
            )
            repo.create_session(
                "ylfego",
                "e" * 64,
                expires_at=now + timedelta(hours=1),
                now=now,
            )
            assert repo.delete_expired_sessions(now=now) == 1
            assert repo.revoke_session("e" * 64) is True
            assert repo.revoke_session("e" * 64) is False

    with sessions() as session:
        assert list(session.scalars(select(AuthSessionRecord))) == []


def test_raw_session_token_is_never_persisted() -> None:
    sessions = make_sessions()
    raw_token = "raw-browser-session-token"
    token_hash = "f" * 64
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    with sessions() as session:
        with session.begin():
            repo = AuthRepository(session)
            repo.set_password("ylfego", "encoded-password-hash", now=now)
            repo.create_session(
                "ylfego",
                token_hash,
                expires_at=now + timedelta(hours=12),
                now=now,
            )

    with sessions() as session:
        record = session.scalar(select(AuthSessionRecord))

    assert record is not None
    assert record.token_hash == token_hash
    assert raw_token not in record.token_hash
