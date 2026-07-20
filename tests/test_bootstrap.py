from trading_agent.config import Settings


def test_settings_have_safe_defaults() -> None:
    settings = Settings()

    assert settings.environment == "test"
    assert settings.enable_order_execution is False
    assert settings.primary_vision_provider == "codex"
    assert settings.fallback_vision_provider == "kimi"
