from trading_agent.api.app import create_app
from trading_agent.config import Settings
from trading_agent.providers.codex import CodexVisionProvider
from trading_agent.providers.factory import configured_vision_provider
from trading_agent.market.providers.akshare import AkShareMarketDataProvider
from trading_agent.market.providers.composite import FreeMarketDataResolver
from trading_agent.market.providers.tqsdk import TqSdkMarketDataProvider
from trading_agent.workflows.activities import _provider


def test_settings_have_safe_defaults() -> None:
    settings = Settings()

    assert settings.environment == "test"
    assert settings.enable_order_execution is False
    assert settings.primary_vision_provider == "codex"
    assert settings.kimi_model == "kimi-k3"
    assert not hasattr(settings, "fallback_vision_provider")
    assert not hasattr(settings, "kimi_external_isolation_verified")
    assert not hasattr(settings, "kimi_isolation_provider")
    assert settings.market_data_provider == "none"
    assert settings.tqsdk_username is None
    assert settings.tqsdk_password is None


def test_provider_factory_honors_explicit_codex_runtime_contract(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TRADING_AGENT_CODEX_MODEL", "gpt-test")
    monkeypatch.setenv("TRADING_AGENT_CODEX_MODEL_PROVIDER", "private-provider")
    monkeypatch.setenv(
        "TRADING_AGENT_CODEX_PROVIDER_BASE_URL",
        "https://provider.example/v1",
    )
    monkeypatch.setenv("TRADING_AGENT_CODEX_PROVIDER_ENV_KEY", "PRIVATE_KEY")

    provider = _provider(
        {
            "agent_backend": {
                "backend_id": "codex",
                "model_id": "gpt-test",
            }
        }
    )

    assert isinstance(provider, CodexVisionProvider)
    assert provider.model == "gpt-test"
    assert provider.model_provider == "private-provider"
    assert provider.provider_base_url == "https://provider.example/v1"
    assert provider.provider_env_key == "PRIVATE_KEY"


def test_evaluation_provider_factory_honors_the_same_codex_runtime_contract(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TRADING_AGENT_CODEX_MODEL", "gpt-eval")
    monkeypatch.setenv("TRADING_AGENT_CODEX_MODEL_PROVIDER", "private-provider")
    monkeypatch.setenv(
        "TRADING_AGENT_CODEX_PROVIDER_BASE_URL",
        "https://provider.example/v1",
    )
    monkeypatch.setenv("TRADING_AGENT_CODEX_PROVIDER_ENV_KEY", "PRIVATE_KEY")

    provider = configured_vision_provider("codex", model="gpt-eval")

    assert isinstance(provider, CodexVisionProvider)
    assert provider.model == "gpt-eval"
    assert provider.model_provider == "private-provider"
    assert provider.provider_base_url == "https://provider.example/v1"
    assert provider.provider_env_key == "PRIVATE_KEY"


def test_api_uses_the_same_configured_provider_factory(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TRADING_AGENT_CODEX_MODEL", "gpt-api-test")
    monkeypatch.setenv("TRADING_AGENT_CODEX_MODEL_PROVIDER", "api-provider")
    monkeypatch.setenv(
        "TRADING_AGENT_CODEX_PROVIDER_BASE_URL",
        "https://api-provider.example/v1",
    )
    monkeypatch.setenv("TRADING_AGENT_CODEX_PROVIDER_ENV_KEY", "API_PROVIDER_KEY")

    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        storage_root=tmp_path,
    )

    provider = app.state.vision_provider
    assert isinstance(provider, CodexVisionProvider)
    assert provider.model == "gpt-api-test"
    assert provider.model_provider == "api-provider"


def test_api_builds_the_configured_free_market_data_resolver(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("TRADING_AGENT_MARKET_DATA_PROVIDER", "free")
    monkeypatch.setenv("TRADING_AGENT_TQSDK_USERNAME", "free-user")
    monkeypatch.setenv("TRADING_AGENT_TQSDK_PASSWORD", "free-password")
    monkeypatch.delenv("TRADING_AGENT_MARKET_DATA_URL", raising=False)

    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        storage_root=tmp_path,
    )

    resolver = app.state.market_data_resolver
    assert isinstance(resolver, FreeMarketDataResolver)
    assert isinstance(resolver.providers[0], TqSdkMarketDataProvider)
    assert isinstance(resolver.providers[1], AkShareMarketDataProvider)
