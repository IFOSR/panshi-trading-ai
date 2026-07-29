from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from trading_agent.auth.passwords import hash_password, verify_password
from trading_agent.auth.repository import AuthRepository
from trading_agent.auth.tokens import digest_session_token, generate_session_token


SESSION_LIFETIME = timedelta(hours=12)
_DUMMY_PASSWORD_HASH = hash_password("panshi-invalid-account")


class InvalidCredentials(RuntimeError):
    pass


class InvalidSession(RuntimeError):
    pass


class AuthService:
    def __init__(self, session: Session) -> None:
        self.repository = AuthRepository(session)

    def login(
        self,
        username: str,
        password: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        authenticated_at = now or datetime.now(timezone.utc)
        self.repository.delete_expired_sessions(now=authenticated_at)
        user = self.repository.get_user_credentials(username)
        encoded_hash = (
            user["password_hash"] if user is not None else _DUMMY_PASSWORD_HASH
        )
        password_matches = verify_password(password, encoded_hash)
        if user is None or not user["is_active"] or not password_matches:
            raise InvalidCredentials

        raw_token = generate_session_token()
        expires_at = authenticated_at + SESSION_LIFETIME
        self.repository.create_session(
            user["username"],
            digest_session_token(raw_token),
            expires_at=expires_at,
            now=authenticated_at,
        )
        return {
            "username": user["username"],
            "session_token": raw_token,
            "expires_at": expires_at,
        }

    def validate_session(
        self,
        raw_token: str | None,
        *,
        now: datetime | None = None,
    ) -> dict:
        if not raw_token:
            raise InvalidSession
        checked_at = now or datetime.now(timezone.utc)
        self.repository.delete_expired_sessions(now=checked_at)
        session = self.repository.validate_session(
            digest_session_token(raw_token),
            now=checked_at,
        )
        if session is None:
            raise InvalidSession
        return {
            "username": session["username"],
            "expires_at": session["expires_at"],
        }

    def logout(self, raw_token: str | None) -> None:
        if raw_token:
            self.repository.revoke_session(digest_session_token(raw_token))
