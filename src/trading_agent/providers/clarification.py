"""Clarification provider backed by DeepSeek (OpenAI-compatible HTTP API)."""

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trading_agent.clarification.models import (
    ClarificationFact,
    ClarificationProposal,
)
from trading_agent.clarification.prompts import render_clarification_prompt
from trading_agent.providers.base import (
    ClarificationRequest,
    ProviderResponseError,
    ProviderUnavailable,
)
from trading_agent.providers.deepseek import (
    DEFAULT_BASE_URL,
    DEFAULT_ENV_KEY,
    DEFAULT_MODEL,
    DeepSeekClarificationProvider,
    _HttpRunner,
    _parse_json_object,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _FactExtraction(_StrictModel):
    question_id: str = Field(min_length=1, max_length=120)
    field: str = Field(min_length=1, max_length=80)
    value: bool | float | str
    explanation: str = Field(min_length=1, max_length=500)


class _ClarificationExtraction(_StrictModel):
    facts: list[_FactExtraction]
    unresolved_question_ids: list[str]
    interpretation: str = Field(min_length=1, max_length=2000)


__all__ = [
    "DeepSeekClarificationProvider",
    "DEFAULT_BASE_URL",
    "DEFAULT_ENV_KEY",
    "DEFAULT_MODEL",
    "_HttpRunner",
    "_parse_json_object",
    "_ClarificationExtraction",
    "ProviderResponseError",
    "ProviderUnavailable",
    "render_clarification_prompt",
    "ClarificationFact",
    "ClarificationProposal",
]
