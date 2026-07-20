from datetime import datetime, timedelta
from pathlib import Path

from pydantic import BaseModel


class RetainedAnalysis(BaseModel):
    image_path: Path
    image_sha256: str
    created_at: datetime
    retention_days: int
    evidence: dict[str, object]
    decision: dict[str, object]


class RetentionResult(BaseModel):
    raw_image_deleted: bool
    image_sha256: str
    evidence: dict[str, object]
    decision: dict[str, object]


def expire_raw_image(item: RetainedAnalysis, now: datetime) -> RetentionResult:
    expired = now >= item.created_at + timedelta(days=item.retention_days)
    deleted = False
    if expired and item.image_path.exists():
        item.image_path.unlink()
        deleted = True
    return RetentionResult(
        raw_image_deleted=deleted,
        image_sha256=item.image_sha256,
        evidence=item.evidence,
        decision=item.decision,
    )
