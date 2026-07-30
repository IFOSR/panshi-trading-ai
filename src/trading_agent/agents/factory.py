from pathlib import Path

from trading_agent.agents.models import AgentRuntime
from trading_agent.agents.registry import (
    AgentBackendRegistry,
    configured_agent_backend_manifests,
)
from trading_agent.config import Settings
from trading_agent.providers.clarification import CodexClarificationProvider
from trading_agent.providers.codex import CodexVisionProvider
from trading_agent.providers.conversation import CodexConversationProvider
from trading_agent.providers.kimi import KimiVisionProvider
from trading_agent.providers.kimi_text import (
    KimiClarificationProvider,
    KimiConversationProvider,
)


def configured_agent_backend_registry(
    settings: Settings | None = None,
    *,
    kimi_config_path: Path | None = None,
) -> AgentBackendRegistry:
    resolved = settings or Settings()
    manifests = configured_agent_backend_manifests(
        codex_model=resolved.codex_model,
        kimi_config_path=kimi_config_path,
    )

    def runtime_factory(backend_id: str, model_id: str) -> AgentRuntime:
        if backend_id == "codex":
            return AgentRuntime(
                backend_id=backend_id,
                model_id=model_id,
                vision=CodexVisionProvider(
                    model=model_id,
                    model_provider=resolved.codex_model_provider,
                    provider_base_url=resolved.codex_provider_base_url,
                    provider_env_key=resolved.codex_provider_env_key,
                ),
                clarification=CodexClarificationProvider(
                    model=model_id,
                    model_provider=resolved.codex_model_provider,
                    provider_base_url=resolved.codex_provider_base_url,
                    provider_env_key=resolved.codex_provider_env_key,
                ),
                conversation=CodexConversationProvider(
                    model=model_id,
                    model_provider=resolved.codex_model_provider,
                    provider_base_url=resolved.codex_provider_base_url,
                    provider_env_key=resolved.codex_provider_env_key,
                ),
            )
        if backend_id == "kimi":
            return AgentRuntime(
                backend_id=backend_id,
                model_id=model_id,
                vision=KimiVisionProvider(model=model_id),
                clarification=KimiClarificationProvider(model=model_id),
                conversation=KimiConversationProvider(model=model_id),
            )
        raise ValueError(f"unknown agent backend: {backend_id}")

    return AgentBackendRegistry(
        manifests=manifests,
        runtime_factory=runtime_factory,
    )
