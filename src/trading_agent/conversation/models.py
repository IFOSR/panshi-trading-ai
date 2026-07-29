from typing import Literal

from pydantic import BaseModel, Field


class ConversationMessage(BaseModel):
    message_id: str
    role: Literal["user", "assistant", "system"]
    message_type: str
    content: str = Field(min_length=1, max_length=12000)
    created_at: str
    analysis_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class ConversationRequest(BaseModel):
    case_id: str
    source_analysis_id: str
    user_message: str = Field(min_length=1, max_length=4000)
    strategy_manifest: dict[str, object]
    decision: dict[str, object]
    milestones: list[dict[str, object]]
    rendered: dict[str, object]


class ConversationReply(BaseModel):
    source_analysis_id: str
    answer: str = Field(min_length=1, max_length=8000)
    suggested_questions: list[str] = Field(default_factory=list)
    provider: str
    model: str
