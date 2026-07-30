from dataclasses import dataclass

from pydantic import BaseModel

from trading_agent.providers.base import (
    ClarificationProvider,
    ConversationProvider,
    VisionProvider,
)


class AgentModelManifest(BaseModel):
    model_id: str
    display_name: str
    capabilities: list[str]
    available: bool
    unavailable_reason: str | None = None


class AgentBackendManifest(BaseModel):
    backend_id: str
    display_name: str
    default_model_id: str
    capabilities: list[str]
    available: bool
    unavailable_reason: str | None = None
    models: list[AgentModelManifest]


@dataclass(frozen=True)
class AgentRuntime:
    backend_id: str
    model_id: str
    vision: VisionProvider
    clarification: ClarificationProvider
    conversation: ConversationProvider
