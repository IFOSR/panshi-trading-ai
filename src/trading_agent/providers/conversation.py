"""Conversation provider backed by DeepSeek (OpenAI-compatible HTTP API)."""

from pydantic import BaseModel, ConfigDict, Field

from trading_agent.conversation.models import (
    ConversationReply,
    ConversationRequest,
)
from trading_agent.providers.base import (
    ProviderResponseError,
    ProviderUnavailable,
)
from trading_agent.providers.deepseek import (
    DEFAULT_BASE_URL,
    DEFAULT_ENV_KEY,
    DEFAULT_MODEL,
    DeepSeekConversationProvider,
    _HttpRunner,
    _parse_json_object,
    render_conversation_prompt,
)


class _StrictConversationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=8000)
    suggested_questions: list[str] = Field(max_length=4)


__all__ = [
    "DeepSeekConversationProvider",
    "DEFAULT_BASE_URL",
    "DEFAULT_ENV_KEY",
    "DEFAULT_MODEL",
    "_HttpRunner",
    "_parse_json_object",
    "render_conversation_prompt",
    "_StrictConversationOutput",
    "ConversationReply",
    "ConversationRequest",
    "ProviderResponseError",
    "ProviderUnavailable",
]
