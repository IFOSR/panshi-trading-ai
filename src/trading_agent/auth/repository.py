from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from trading_agent.db.models import AuthSessionRecord, UserRecord


def normalize_username(username: str) -> str:
    return username.strip().lower()


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def set_password(
        self,
        username: str,
        password_hash: str,
        *,
        now: datetime | None = None,
    ) -> dict:
        normalized = normalize_username(username)
        changed_at = now or datetime.now(timezone.utc)
        user = self.session.scalar(
            select(UserRecord).where(UserRecord.username == normalized)
        )
        if user is None:
            user = UserRecord(
                user_id=str(uuid4()),
                username=normalized,
                password_hash=password_hash,
                is_active=True,
                created_at=changed_at,
                updated_at=changed_at,
            )
            self.session.add(user)
        else:
            user.password_hash = password_hash
            user.updated_at = changed_at
            self._delete_user_sessions(user.user_id)
        self.session.flush()
        return self._user_payload(user)

    def get_user_credentials(self, username: str) -> dict | None:
        user = self.session.scalar(
            select(UserRecord).where(
                UserRecord.username == normalize_username(username)
            )
        )
        if user is None:
            return None
        return {
            "user_id": user.user_id,
            "username": user.username,
            "password_hash": user.password_hash,
            "is_active": user.is_active,
        }

    def set_active(
        self,
        username: str,
        active: bool,
        *,
        now: datetime | None = None,
    ) -> bool:
        user = self.session.scalar(
            select(UserRecord).where(
                UserRecord.username == normalize_username(username)
            )
        )
        if user is None:
            return False
        user.is_active = active
        user.updated_at = now or datetime.now(timezone.utc)
        if not active:
            self._delete_user_sessions(user.user_id)
        self.session.flush()
        return True

    def create_session(
        self,
        username: str,
        token_hash: str,
        *,
        expires_at: datetime,
        now: datetime | None = None,
    ) -> dict:
        user = self.session.scalar(
            select(UserRecord).where(
                UserRecord.username == normalize_username(username)
            )
        )
        if user is None:
            raise KeyError(username)
        created_at = now or datetime.now(timezone.utc)
        record = AuthSessionRecord(
            session_id=str(uuid4()),
            user_id=user.user_id,
            token_hash=token_hash,
            created_at=created_at,
            expires_at=expires_at,
        )
        self.session.add(record)
        self.session.flush()
        return {
            "session_id": record.session_id,
            "username": user.username,
            "created_at": record.created_at,
            "expires_at": record.expires_at,
        }

    def validate_session(
        self,
        token_hash: str,
        *,
        now: datetime | None = None,
    ) -> dict | None:
        checked_at = now or datetime.now(timezone.utc)
        result = self.session.execute(
            select(AuthSessionRecord, UserRecord)
            .join(UserRecord, UserRecord.user_id == AuthSessionRecord.user_id)
            .where(
                AuthSessionRecord.token_hash == token_hash,
                AuthSessionRecord.expires_at > checked_at,
                UserRecord.is_active.is_(True),
            )
        ).one_or_none()
        if result is None:
            return None
        auth_session, user = result
        return {
            "user_id": user.user_id,
            "username": user.username,
            "session_id": auth_session.session_id,
            "expires_at": auth_session.expires_at,
        }

    def delete_expired_sessions(self, *, now: datetime | None = None) -> int:
        result = self.session.execute(
            delete(AuthSessionRecord).where(
                AuthSessionRecord.expires_at <= (now or datetime.now(timezone.utc))
            )
        )
        self.session.flush()
        return result.rowcount or 0

    def revoke_session(self, token_hash: str) -> bool:
        result = self.session.execute(
            delete(AuthSessionRecord).where(AuthSessionRecord.token_hash == token_hash)
        )
        self.session.flush()
        return bool(result.rowcount)

    def _delete_user_sessions(self, user_id: str) -> None:
        self.session.execute(
            delete(AuthSessionRecord).where(AuthSessionRecord.user_id == user_id)
        )

    @staticmethod
    def _user_payload(user: UserRecord) -> dict:
        return {
            "user_id": user.user_id,
            "username": user.username,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }
