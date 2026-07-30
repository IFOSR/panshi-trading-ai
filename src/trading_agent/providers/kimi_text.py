from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trading_agent.clarification.models import (
    ClarificationFact,
    ClarificationProposal,
)
from trading_agent.clarification.prompts import render_clarification_prompt
from trading_agent.conversation.models import (
    ConversationReply,
    ConversationRequest,
)
from trading_agent.providers.base import (
    ClarificationRequest,
    ProviderResponseError,
)
from trading_agent.providers.conversation import render_conversation_prompt
from trading_agent.providers.kimi_acp import AcpCompletionClient, KimiAcpClient


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _ConversationOutput(_StrictModel):
    answer: str = Field(min_length=1, max_length=8000)
    suggested_questions: list[str] = Field(max_length=4)


class _FactOutput(_StrictModel):
    question_id: str = Field(min_length=1, max_length=120)
    field: str = Field(min_length=1, max_length=80)
    value: bool | float | str
    explanation: str = Field(min_length=1, max_length=500)


class _ClarificationOutput(_StrictModel):
    facts: list[_FactOutput]
    unresolved_question_ids: list[str]
    interpretation: str = Field(min_length=1, max_length=2000)


class _KimiPromptProvider:
    def __init__(
        self,
        *,
        model: str,
        client: AcpCompletionClient | None = None,
        timeout_seconds: float = 120.0,
    ) -> None:
        self.model = model
        self.client = client or KimiAcpClient(
            model=model,
            timeout_seconds=timeout_seconds,
        )

    def _complete(self, prompt: str) -> str:
        return self.client.complete(prompt)


class KimiConversationProvider(_KimiPromptProvider):
    def reply(self, request: ConversationRequest) -> ConversationReply:
        try:
            output = _ConversationOutput.model_validate_json(
                self._complete(render_conversation_prompt(request))
            )
        except ValidationError as exc:
            raise ProviderResponseError(
                "kimi returned invalid conversation output"
            ) from exc
        return ConversationReply(
            source_analysis_id=request.source_analysis_id,
            answer=output.answer,
            suggested_questions=output.suggested_questions,
            provider="kimi",
            model=self.model,
        )


class KimiClarificationProvider(_KimiPromptProvider):
    def interpret(self, request: ClarificationRequest) -> ClarificationProposal:
        try:
            output = _ClarificationOutput.model_validate_json(
                self._complete(render_clarification_prompt(request))
            )
        except ValidationError as exc:
            raise ProviderResponseError(
                "kimi returned invalid clarification"
            ) from exc
        question_by_id = {
            question.question_id: question for question in request.questions
        }
        facts: list[ClarificationFact] = []
        try:
            for extracted in output.facts:
                question = question_by_id.get(extracted.question_id)
                if (
                    question is None
                    or extracted.field not in question.allowed_fact_fields
                ):
                    raise ValueError(
                        "clarification fact is outside open questions"
                    )
                facts.append(
                    ClarificationFact(
                        **extracted.model_dump(),
                        resolves_blockers=question.blocking_issues,
                    )
                )
            if not set(output.unresolved_question_ids) <= set(question_by_id):
                raise ValueError(
                    "unresolved clarification question is not open"
                )
        except (ValidationError, ValueError) as exc:
            raise ProviderResponseError(
                "kimi returned clarification outside the allowed questions"
            ) from exc
        return ClarificationProposal(
            clarification_id=request.clarification_id,
            source_analysis_id=request.source_analysis_id,
            user_message=request.user_message,
            facts=facts,
            unresolved_question_ids=output.unresolved_question_ids,
            interpretation=output.interpretation,
            provider="kimi",
            model=self.model,
        )
