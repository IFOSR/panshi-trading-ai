"""Entitlement models."""

from datetime import datetime

from pydantic import BaseModel


class EntitlementResult(BaseModel):
    accessible: bool
    reason: str = "no_entitlement"
    entitlement_id: str | None = None
    access_type: str | None = None
    expires_at: datetime | None = None


class UserEntitlementInfo(BaseModel):
    entitlement_id: str
    strategy_id: str
    version: str
    access_type: str
    status: str
    expires_at: datetime | None = None
