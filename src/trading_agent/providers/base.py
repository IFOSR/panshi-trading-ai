from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from trading_agent.domain.evidence import ScreenshotEvidence


class ProviderUnavailable(RuntimeError):
    """Raised when a configured multimodal provider cannot serve the request."""


class ProviderResponseError(RuntimeError):
    """Raised when a provider returns an invalid or unsafe response."""


class VisionRequest(BaseModel):
    prompt_version: str
    image_paths: list[Path] = Field(min_length=1)
    user_context: str | None = None


class VisionProvider(Protocol):
    def analyze(self, request: VisionRequest) -> ScreenshotEvidence:
        ...

