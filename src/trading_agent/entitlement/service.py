"""Entitlement service - core business logic."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from trading_agent.db.models import UserEntitlementRecord
from trading_agent.entitlement.models import EntitlementResult, UserEntitlementInfo
from trading_agent.entitlement.repository import EntitlementRepository


class EntitlementService:
    def __init__(self, session: Session) -> None:
        self.repo = EntitlementRepository(session)

    def check_access(
        self,
        user_id: str,
        strategy_id: str,
        version: str | None = None,
    ) -> EntitlementResult:
        # First try active records
        records = self.repo.find_active(user_id, strategy_id)
        if version:
            records = [r for r in records if r.version == version]
        if records:
            best = records[0]
            return EntitlementResult(
                accessible=True,
                reason="active",
                entitlement_id=best.entitlement_id,
                access_type=best.access_type,
                expires_at=best.expires_at,
            )

        # Check if user has expired entitlements (by status or by date expiry)
        all_records = self.repo.find_any(user_id, strategy_id)
        if version:
            all_records = [r for r in all_records if r.version == version]
        now = datetime.now(timezone.utc)
        for r in all_records:
            if r.status == "expired":
                return EntitlementResult(accessible=False, reason="expired")
            if r.expires_at is not None:
                expires = r.expires_at.replace(tzinfo=timezone.utc) if r.expires_at.tzinfo is None else r.expires_at
                if expires <= now:
                    return EntitlementResult(accessible=False, reason="expired")

        return EntitlementResult(accessible=False, reason="no_entitlement")

    def grant_access(
        self,
        user_id: str,
        strategy_id: str,
        version: str,
        access_type: str,
        order_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> UserEntitlementInfo:
        record = UserEntitlementRecord(
            entitlement_id=str(uuid4()),
            user_id=user_id,
            strategy_id=strategy_id,
            version=version,
            access_type=access_type,
            status="active",
            order_id=order_id,
            expires_at=expires_at,
        )
        self.repo.save(record)
        return UserEntitlementInfo(
            entitlement_id=record.entitlement_id,
            strategy_id=record.strategy_id,
            version=record.version,
            access_type=record.access_type,
            status=record.status,
            expires_at=record.expires_at,
        )

    def list_user_entitlements(self, user_id: str) -> list[UserEntitlementInfo]:
        records = self.repo.list_by_user(user_id)
        return [
            UserEntitlementInfo(
                entitlement_id=r.entitlement_id,
                strategy_id=r.strategy_id,
                version=r.version,
                access_type=r.access_type,
                status=r.status,
                expires_at=r.expires_at,
            )
            for r in records
        ]

    def expire_overdue_entitlements(self) -> int:
        return self.repo.expire_overdue()
