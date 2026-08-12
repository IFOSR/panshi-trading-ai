"""DeepSeek multimodal provider via the OpenAI-compatible HTTP API.

Primary provider for vision analysis, clarification, and conversation.
Falls back to Kimi when unavailable.
"""

import base64
import json
import os
from pathlib import Path
from typing import Callable

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
from trading_agent.domain.evidence import (
    Evidence,
    FactSupport,
    ScreenshotEvidence,
    StrategyEvidenceFacts,
)
from trading_agent.providers.base import (
    ClarificationRequest,
    ProviderResponseError,
    ProviderUnavailable,
    VisionRequest,
)
from trading_agent.providers.extraction import (
    ScreenshotExtraction,
    enforce_safe_usage,
)
from trading_agent.vision.image_quality import inspect_original_image
from trading_agent.vision.prompts import provider_prompt_sha256, render_provider_prompt

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - httpx is a declared dependency
    httpx = None  # type: ignore[assignment]

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_ENV_KEY = "DEEPSEEK_API_KEY"


class _ClarificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: list[dict]
    unresolved_question_ids: list[str]
    interpretation: str = Field(min_length=1, max_length=2000)


class _ConversationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=8000)
    suggested_questions: list[str] = Field(max_length=4)


def render_conversation_prompt(request: ConversationRequest) -> str:
    payload = {
        "strategy_manifest": request.strategy_manifest,
        "decision": request.decision,
        "milestones": request.milestones,
        "rendered": request.rendered,
    }
    return "\n".join(
        [
            "你是磐石交易AI的结论解释器。",
            "只能解释给定的不可变策略结果，不得修改动作、策略、里程碑或风险结论。",
            "如果用户提出新的事实、要求刷新行情或上传新图，明确说明需要重新分析。",
            "回答使用简洁中文，引用可见的策略步骤，不展示隐藏思维过程。",
            "返回严格JSON。",
            f"source_analysis_id: {request.source_analysis_id}",
            "analysis:",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            "user_question:",
            request.user_message,
        ]
    )


class _HttpRunner:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        env_key: str = DEFAULT_ENV_KEY,
        timeout_seconds: float = 180.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.env_key = env_key
        self.timeout_seconds = timeout_seconds

    def complete(
        self,
        messages: list[dict],
        *,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.0,
    ) -> str:
        if httpx is None:
            raise ProviderUnavailable("httpx is not installed")
        api_key = os.environ.get(self.env_key)
        if not api_key:
            raise ProviderUnavailable(
                f"deepseek provider credential {self.env_key} is not configured"
            )
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"deepseek provider unavailable: {exc}") from exc
        if response.status_code != 200:
            raise ProviderUnavailable(
                "deepseek provider failed with status "
                f"{response.status_code}: {response.text[:500]}"
            )
        try:
            payload = response.json()
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderResponseError(
                "deepseek returned an unexpected response"
            ) from exc


def _parse_json_object(output: str, model_name: str, purpose: str):
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(
            f"deepseek returned invalid {purpose}"
        ) from exc


class DeepSeekVisionProvider:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        runner: _HttpRunner | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        env_key: str = DEFAULT_ENV_KEY,
        timeout_seconds: float = 180.0,
    ) -> None:
        self.model = model
        self.runner = runner or _HttpRunner(
            base_url=base_url,
            env_key=env_key,
            timeout_seconds=timeout_seconds,
        )

    def analyze(self, request: VisionRequest) -> ScreenshotEvidence:
        if not request.privacy_assessment.safe_for_model:
            raise ValueError("privacy assessment blocks model transmission")
        artifacts = [
            inspect_original_image(path, storage_root=request.storage_root)
            for path in request.image_paths
        ]
        image_suffixes = [artifact.path.suffix.lower() for artifact in artifacts]
        prompt = render_provider_prompt(
            request.prompt_version,
            provider="deepseek",
            image_suffixes=image_suffixes,
        )
        prompt_hash = provider_prompt_sha256(
            request.prompt_version,
            provider="deepseek",
            image_suffixes=image_suffixes,
        )

        content: list[dict] = []
        for artifact in artifacts:
            media_type = "image/png" if artifact.path.suffix.lower() == ".png" else "image/jpeg"
            encoded = base64.b64encode(artifact.path.read_bytes()).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{media_type};base64,{encoded}",
                    },
                }
            )
        content.append({"type": "text", "text": prompt})

        try:
            output = self.runner.complete(
                [{"role": "user", "content": content}],
                model=self.model,
            )
        except ProviderUnavailable:
            raise

        data = _parse_json_object(output, self.model, "screenshot evidence")
        try:
            extraction = ScreenshotExtraction.model_validate(data)
        except ValidationError as exc:
            raise ProviderResponseError(
                "deepseek returned invalid screenshot evidence"
            ) from exc

        observations = []
        for observation in extraction.observations:
            if observation.source_image_index >= len(request.image_paths):
                raise ProviderResponseError(
                    "deepseek referenced an out-of-range source image"
                )
            observations.append(
                Evidence(
                    evidence_id=observation.evidence_id,
                    kind=observation.kind,
                    value=observation.conclusion,
                    confidence=observation.confidence,
                    provenance=f"deepseek:{self.model}",
                    visible_text=observation.visible_text,
                    image_path=str(
                        request.image_paths[observation.source_image_index]
                    ),
                    evidence_description=observation.evidence_description,
                )
            )
        return ScreenshotEvidence(
            image_role=extraction.image_role,
            contract=extraction.contract,
            timeframe=extraction.timeframe,
            cutoff_time=extraction.cutoff_time,
            last_bar_closed=extraction.last_bar_closed,
            indicators=extraction.indicators.model_dump(mode="json"),
            blocking_issues=list(extraction.blocking_issues),
            provider="deepseek",
            model=self.model,
            prompt_version=request.prompt_version,
            prompt_sha256=prompt_hash,
            image_sha256=artifacts[0].sha256,
            source_image_path=str(request.image_paths[0]),
            allowed_usage=enforce_safe_usage(extraction),
            field_provenance={
                "contract": "structured_market_data",
                "strategy_facts.trend_bias": "vision_verified",
                "strategy_facts.price_location": "vision_verified",
                "strategy_facts.volume_state": "vision_verified",
                "strategy_facts.momentum_state": "vision_verified",
                "strategy_facts.position_behavior": "vision_verified",
                "strategy_facts.price_confirmation": "vision_verified",
            },
            observations=observations,
            strategy_facts=StrategyEvidenceFacts(
                trend_bias=extraction.strategy_facts.trend_bias,
                price_location=extraction.strategy_facts.price_location,
                volume_state=extraction.strategy_facts.volume_state,
                momentum_state=extraction.strategy_facts.momentum_state,
                position_behavior=extraction.strategy_facts.position_behavior,
                price_confirmation=extraction.strategy_facts.price_confirmation,
                price_confirmation_direction=extraction.strategy_facts.price_confirmation_direction,
                price_confirmation_type=extraction.strategy_facts.price_confirmation_type,
            ),
            strategy_fact_support={
                field: FactSupport(
                    confidence=support.confidence,
                    evidence_refs=list(support.evidence_refs),
                )
                for field, support in extraction.strategy_fact_support.model_dump().items()
                if support is not None
            },
        )


class DeepSeekClarificationProvider:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        runner: _HttpRunner | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        env_key: str = DEFAULT_ENV_KEY,
        timeout_seconds: float = 180.0,
    ) -> None:
        self.model = model
        self.runner = runner or _HttpRunner(
            base_url=base_url,
            env_key=env_key,
            timeout_seconds=timeout_seconds,
        )

    def interpret(self, request: ClarificationRequest) -> ClarificationProposal:
        try:
            output = self.runner.complete(
                [
                    {
                        "role": "user",
                        "content": render_clarification_prompt(request),
                    }
                ],
                model=self.model,
            )
        except ProviderUnavailable:
            raise

        data = _parse_json_object(output, self.model, "clarification")
        try:
            extraction = _ClarificationOutput.model_validate(data)
            facts: list[ClarificationFact] = []
            for raw in extraction.facts:
                facts.append(ClarificationFact.model_validate(raw))
        except (ValidationError, ValueError) as exc:
            raise ProviderResponseError(
                "deepseek returned invalid clarification"
            ) from exc

        question_by_id = {
            question.question_id: question for question in request.questions
        }
        try:
            for fact in facts:
                question = question_by_id.get(fact.question_id)
                if question is None or fact.field not in question.allowed_fact_fields:
                    raise ValueError("clarification fact is outside open questions")
                fact.resolves_blockers = question.blocking_issues
            if not set(extraction.unresolved_question_ids) <= set(question_by_id):
                raise ValueError("unresolved clarification question is not open")
        except ValueError as exc:
            raise ProviderResponseError(
                "deepseek returned clarification outside the allowed questions"
            ) from exc

        return ClarificationProposal(
            clarification_id=request.clarification_id,
            source_analysis_id=request.source_analysis_id,
            user_message=request.user_message,
            facts=facts,
            unresolved_question_ids=list(extraction.unresolved_question_ids),
            interpretation=extraction.interpretation,
            provider="deepseek",
            model=self.model,
        )


class DeepSeekConversationProvider:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        runner: _HttpRunner | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        env_key: str = DEFAULT_ENV_KEY,
        timeout_seconds: float = 180.0,
    ) -> None:
        self.model = model
        self.runner = runner or _HttpRunner(
            base_url=base_url,
            env_key=env_key,
            timeout_seconds=timeout_seconds,
        )

    def reply(self, request: ConversationRequest) -> ConversationReply:
        try:
            output = self.runner.complete(
                [
                    {
                        "role": "user",
                        "content": render_conversation_prompt(request),
                    }
                ],
                model=self.model,
            )
        except ProviderUnavailable:
            raise

        data = _parse_json_object(output, self.model, "conversation output")
        try:
            parsed = _ConversationOutput.model_validate(data)
        except ValidationError as exc:
            raise ProviderResponseError(
                "deepseek returned invalid conversation output"
            ) from exc

        return ConversationReply(
            source_analysis_id=request.source_analysis_id,
            answer=parsed.answer,
            suggested_questions=parsed.suggested_questions,
            provider="deepseek",
            model=self.model,
        )
