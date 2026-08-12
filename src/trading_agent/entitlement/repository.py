"""Entitlement data access."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from trading_agent.db.models import UserEntitlementRecord


class EntitlementRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_active(
        self, user_id: str, strategy_id: str,
    ) -> list[UserEntitlementRecord]:
        now = datetime.now(timezone.utc)
        return (
            self.session.query(UserEntitlementRecord)
            .filter(
                UserEntitlementRecord.user_id == user_id,
                UserEntitlementRecord.strategy_id == strategy_id,
                UserEntitlementRecord.status == "active",
                (
                    UserEntitlementRecord.expires_at.is_(None)
                    | (UserEntitlementRecord.expires_at > now)
                ),
            )
            .all()
        )

    def find_any(
        self, user_id: str, strategy_id: str,
    ) -> list[UserEntitlementRecord]:
        return (
            self.session.query(UserEntitlementRecord)
            .filter(
                UserEntitlementRecord.user_id == user_id,
                UserEntitlementRecord.strategy_id == strategy_id,
            )
            .all()
        )

    def list_by_user(self, user_id: str) -> list[UserEntitlementRecord]:
        return (
            self.session.query(UserEntitlementRecord)
            .filter(UserEntitlementRecord.user_id == user_id)
            .all()
        )

    def save(self, record: UserEntitlementRecord) -> UserEntitlementRecord:
        self.session.add(record)
        self.session.flush()
        return record

    def expire_overdue(self) -> int:
        now = datetime.now(timezone.utc)
        result = (
            self.session.query(UserEntitlementRecord)
            .filter(
                UserEntitlementRecord.status == "active",
                UserEntitlementRecord.expires_at.isnot(None),
                UserEntitlementRecord.expires_at <= now,
            )
            .update({"status": "expired", "updated_at": now})
        )
        return result
