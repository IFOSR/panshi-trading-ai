import json
import os
import subprocess
import tempfile
from pathlib import Path

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
from trading_agent.providers.codex import (
    ProviderConfig,
    Runner,
    _isolated_codex_config,
    _machine_default_provider,
    _run,
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


class CodexClarificationProvider:
    def __init__(
        self,
        model: str = "gpt-5.6-sol",
        runner: Runner = _run,
        timeout_seconds: float = 120.0,
        model_provider: str | None = None,
        provider_base_url: str | None = None,
        provider_env_key: str | None = None,
    ) -> None:
        override_values = (model_provider, provider_base_url, provider_env_key)
        if any(override_values) and not all(override_values):
            raise ValueError(
                "Codex provider override requires provider, base URL, and env key"
            )
        self.model = model
        self.runner = runner
        self.timeout_seconds = timeout_seconds
        self.model_provider = model_provider
        self.provider_base_url = provider_base_url
        self.provider_env_key = provider_env_key

    def _provider_config(self) -> ProviderConfig | None:
        if self.model_provider is None:
            return _machine_default_provider()
        assert self.provider_base_url is not None
        assert self.provider_env_key is not None
        return (
            self.model_provider,
            {
                "name": self.model_provider,
                "base_url": self.provider_base_url,
                "wire_api": "responses",
                "requires_openai_auth": False,
                "env_key": self.provider_env_key,
            },
        )

    def interpret(self, request: ClarificationRequest) -> ClarificationProposal:
        if self.provider_env_key is not None and not os.environ.get(
            self.provider_env_key
        ):
            raise ProviderUnavailable(
                f"codex provider credential {self.provider_env_key} is not configured"
            )
        provider_config = self._provider_config()
        with tempfile.TemporaryDirectory(
            prefix="trading-agent-clarification-"
        ) as temp_dir:
            isolated_root = Path(temp_dir)
            codex_home = isolated_root / ".codex"
            temp_root = isolated_root / "tmp"
            codex_home.mkdir()
            temp_root.mkdir()
            (codex_home / "config.toml").write_text(
                _isolated_codex_config(provider_config),
                encoding="utf-8",
            )
            schema_path = isolated_root / "schema.json"
            output_path = isolated_root / "output.json"
            schema_path.write_text(
                json.dumps(
                    _ClarificationExtraction.model_json_schema(),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            command = [
                "codex",
                "exec",
                "--strict-config",
                "--skip-git-repo-check",
                "--ephemeral",
                "--ignore-rules",
                "-C",
                str(isolated_root),
                "--model",
                self.model,
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "-",
            ]
            environment = {
                key: value
                for key, value in os.environ.items()
                if key in {"PATH", "LANG", "LC_ALL"}
            }
            environment.update(
                {
                    "HOME": str(isolated_root),
                    "CODEX_HOME": str(codex_home),
                    "TMPDIR": str(temp_root),
                }
            )
            if provider_config is not None:
                env_key = provider_config[1].get("env_key")
                if isinstance(env_key, str) and env_key in os.environ:
                    environment[env_key] = os.environ[env_key]
            try:
                completed = self.runner(
                    command,
                    self.timeout_seconds,
                    isolated_root,
                    render_clarification_prompt(request),
                    environment,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ProviderUnavailable(
                    f"codex clarification provider unavailable: {exc}"
                ) from exc
            if completed.returncode != 0:
                raise ProviderUnavailable(
                    "codex clarification provider failed with exit "
                    f"{completed.returncode}: {completed.stderr.strip()}"
                )
            if not output_path.exists():
                raise ProviderResponseError(
                    "codex clarification provider produced no output"
                )
            try:
                extraction = _ClarificationExtraction.model_validate_json(
                    output_path.read_text(encoding="utf-8")
                )
            except ValidationError as exc:
                raise ProviderResponseError(
                    "codex returned invalid clarification"
                ) from exc

        question_by_id = {
            question.question_id: question for question in request.questions
        }
        facts: list[ClarificationFact] = []
        try:
            for extracted in extraction.facts:
                question = question_by_id.get(extracted.question_id)
                if (
                    question is None
                    or extracted.field not in question.allowed_fact_fields
                ):
                    raise ValueError("clarification fact is outside open questions")
                facts.append(
                    ClarificationFact(
                        **extracted.model_dump(),
                        resolves_blockers=question.blocking_issues,
                    )
                )
            if not set(extraction.unresolved_question_ids) <= set(question_by_id):
                raise ValueError("unresolved clarification question is not open")
        except (ValidationError, ValueError) as exc:
            raise ProviderResponseError(
                "codex returned clarification outside the allowed questions"
            ) from exc
        return ClarificationProposal(
            clarification_id=request.clarification_id,
            source_analysis_id=request.source_analysis_id,
            user_message=request.user_message,
            facts=facts,
            unresolved_question_ids=extraction.unresolved_question_ids,
            interpretation=extraction.interpretation,
            provider="codex",
            model=self.model,
        )
