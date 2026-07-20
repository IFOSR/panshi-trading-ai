from typing import Any

from pydantic import BaseModel, Field

from trading_agent.domain.enums import EvidenceUsage


class Evidence(BaseModel):
    evidence_id: str
    kind: str
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: str
    visible_text: str | None = None
    image_path: str | None = None


class ScreenshotEvidence(BaseModel):
    image_role: str
    instrument: str | None = None
    contract: str | None = None
    timeframe: str | None = None
    cutoff_time: str | None = None
    last_bar_closed: bool | None = None
    indicators: dict[str, Any] = Field(default_factory=dict)
    observations: list[Evidence] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    allowed_usage: EvidenceUsage = EvidenceUsage.QUALITATIVE_ONLY
    provider: str
    model: str
    prompt_version: str
    image_sha256: str

