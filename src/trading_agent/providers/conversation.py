import json
import os
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from trading_agent.conversation.models import (
    ConversationReply,
    ConversationRequest,
)
from trading_agent.providers.base import (
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


class _StrictConversationOutput(BaseModel):
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


class CodexConversationProvider:
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

    def reply(self, request: ConversationRequest) -> ConversationReply:
        if self.provider_env_key is not None and not os.environ.get(
            self.provider_env_key
        ):
            raise ProviderUnavailable(
                f"codex provider credential {self.provider_env_key} is not configured"
            )
        provider_config = self._provider_config()
        with tempfile.TemporaryDirectory(
            prefix="trading-agent-conversation-"
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
                    _StrictConversationOutput.model_json_schema(),
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
                    render_conversation_prompt(request),
                    environment,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ProviderUnavailable(
                    f"codex conversation provider unavailable: {exc}"
                ) from exc
            if completed.returncode != 0:
                raise ProviderUnavailable(
                    "codex conversation provider failed with exit "
                    f"{completed.returncode}: {completed.stderr.strip()}"
                )
            if not output_path.exists():
                raise ProviderResponseError(
                    "codex conversation provider produced no output"
                )
            try:
                output = _StrictConversationOutput.model_validate_json(
                    output_path.read_text(encoding="utf-8")
                )
            except ValidationError as exc:
                raise ProviderResponseError(
                    "codex returned invalid conversation output"
                ) from exc
        return ConversationReply(
            source_analysis_id=request.source_analysis_id,
            answer=output.answer,
            suggested_questions=output.suggested_questions,
            provider="codex",
            model=self.model,
        )
