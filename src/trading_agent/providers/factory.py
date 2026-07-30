from trading_agent.config import Settings
from trading_agent.providers.base import VisionProvider
from trading_agent.providers.codex import CodexVisionProvider
from trading_agent.providers.kimi import KimiVisionProvider


def configured_vision_provider(
    provider: str,
    *,
    model: str | None = None,
    settings: Settings | None = None,
) -> VisionProvider:
    resolved = settings or Settings()
    if provider == "codex":
        configured_model = resolved.codex_model
        if model is not None and model != configured_model:
            raise ValueError(
                "vision evaluation model does not match production Codex model: "
                f"{model!r} != {configured_model!r}"
            )
        return CodexVisionProvider(
            model=configured_model,
            model_provider=resolved.codex_model_provider,
            provider_base_url=resolved.codex_provider_base_url,
            provider_env_key=resolved.codex_provider_env_key,
        )
    if provider == "kimi":
        configured_model = resolved.kimi_model
        if model is not None and model != configured_model:
            raise ValueError(
                "vision evaluation model does not match production Kimi model: "
                f"{model!r} != {configured_model!r}"
            )
        return KimiVisionProvider(model=configured_model)
    raise ValueError(f"unsupported vision provider: {provider}")
