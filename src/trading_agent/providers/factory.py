from trading_agent.config import Settings
from trading_agent.providers.base import VisionProvider
from trading_agent.providers.deepseek import DeepSeekVisionProvider
from trading_agent.providers.fallback import FallbackVisionProvider
from trading_agent.providers.kimi import (
    KimiVisionProvider,
    trusted_external_isolation_checker,
)


def configured_vision_provider(
    provider: str,
    *,
    model: str | None = None,
    settings: Settings | None = None,
) -> VisionProvider:
    resolved = settings or Settings()
    if provider == "deepseek":
        configured_model = resolved.deepseek_model
        if model is not None and model != configured_model:
            raise ValueError(
                "vision evaluation model does not match production DeepSeek model: "
                f"{model!r} != {configured_model!r}"
            )
        return DeepSeekVisionProvider(
            model=configured_model,
            base_url=resolved.deepseek_base_url,
            env_key=resolved.deepseek_env_key,
        )
    if provider == "kimi":
        configured_model = resolved.kimi_model
        if model is not None and model != configured_model:
            raise ValueError(
                "vision evaluation model does not match production Kimi model: "
                f"{model!r} != {configured_model!r}"
            )
        return KimiVisionProvider(
            model=configured_model,
            isolation_checker=trusted_external_isolation_checker(
                verified=resolved.kimi_external_isolation_verified,
                provider=resolved.kimi_isolation_provider,
            ),
        )
    raise ValueError(f"unsupported vision provider: {provider}")


def configured_fallback_provider(
    settings: Settings | None = None,
) -> FallbackVisionProvider:
    resolved = settings or Settings()
    return FallbackVisionProvider(
        primary=configured_vision_provider(
            resolved.primary_vision_provider,
            settings=resolved,
        ),
        fallback=configured_vision_provider(
            resolved.fallback_vision_provider,
            settings=resolved,
        ),
    )
