import json
from pathlib import Path
from subprocess import CompletedProcess

from trading_agent.api.app import create_app
from trading_agent.config import Settings
from trading_agent.providers.base import ProviderUnavailable, VisionRequest
from trading_agent.providers.codex import CodexVisionProvider
from trading_agent.providers.fallback import FallbackVisionProvider
from trading_agent.providers.kimi import KimiVisionProvider
from trading_agent.providers.factory import configured_vision_provider
from trading_agent.market.providers.akshare import AkShareMarketDataProvider
from trading_agent.market.providers.composite import FreeMarketDataResolver
from trading_agent.market.providers.tqsdk import TqSdkMarketDataProvider
from trading_agent.vision.privacy import PrivacyAssessment
from trading_agent.workflows.activities import _provider


FIXTURE = Path("tests/fixtures/charts/daily_boll_macd_volume.png")


def test_settings_have_safe_defaults() -> None:
    settings = Settings()

    assert settings.environment == "test"
    assert settings.enable_order_execution is False
    assert settings.primary_vision_provider == "codex"
    assert settings.fallback_vision_provider == "kimi"
    assert settings.kimi_model == "default"
    assert settings.kimi_external_isolation_verified is False
    assert settings.kimi_isolation_provider is None
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

    provider = _provider()

    assert isinstance(provider, FallbackVisionProvider)
    assert isinstance(provider.primary, CodexVisionProvider)
    assert provider.primary.model == "gpt-test"
    assert provider.primary.model_provider == "private-provider"
    assert provider.primary.provider_base_url == "https://provider.example/v1"
    assert provider.primary.provider_env_key == "PRIVATE_KEY"


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


def test_provider_factory_keeps_kimi_isolation_fail_closed_by_default() -> None:
    provider = _provider()

    assert isinstance(provider, FallbackVisionProvider)
    assert isinstance(provider.fallback, KimiVisionProvider)
    assert provider.fallback.isolation_checker() is False


def test_provider_factory_rejects_incomplete_kimi_isolation_config(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TRADING_AGENT_KIMI_EXTERNAL_ISOLATION_VERIFIED", "true")
    monkeypatch.delenv("TRADING_AGENT_KIMI_ISOLATION_PROVIDER", raising=False)

    provider = _provider()

    assert isinstance(provider, FallbackVisionProvider)
    assert isinstance(provider.fallback, KimiVisionProvider)
    assert provider.fallback.isolation_checker() is False


def test_provider_factory_can_fallback_to_kimi_under_trusted_os_isolation(
    monkeypatch,
) -> None:
    monkeypatch.setenv("TRADING_AGENT_KIMI_MODEL", "kimi-vision-test")
    monkeypatch.setenv("TRADING_AGENT_KIMI_EXTERNAL_ISOLATION_VERIFIED", "true")
    monkeypatch.setenv(
        "TRADING_AGENT_KIMI_ISOLATION_PROVIDER",
        "docker-hardened-worker-v1",
    )
    captured: dict[str, object] = {}
    payload = {
        "image_role": "STATE_DAILY",
        "instrument": None,
        "contract": None,
        "timeframe": "1d",
        "cutoff_time": None,
        "last_bar_closed": None,
        "indicators": {
            "boll": None,
            "macd": None,
            "volume": None,
            "position_behavior": None,
            "notes": [],
        },
        "strategy_facts": {
            "trend_bias": "UNKNOWN",
            "price_location": "UNKNOWN",
            "volume_state": "UNKNOWN",
            "momentum_state": "UNKNOWN",
            "position_behavior": "UNKNOWN",
            "price_confirmation": None,
            "price_confirmation_direction": "UNKNOWN",
            "price_confirmation_type": "UNKNOWN",
        },
        "strategy_fact_support": {
            "trend_bias": None,
            "price_location": None,
            "volume_state": None,
            "momentum_state": None,
            "position_behavior": None,
            "price_confirmation": None,
            "price_confirmation_direction": None,
            "price_confirmation_type": None,
        },
        "observations": [],
        "blocking_issues": ["CONTRACT_MISSING"],
        "allowed_usage": "QUALITATIVE_ONLY",
    }

    def primary_unavailable(request: VisionRequest) -> None:
        raise ProviderUnavailable("codex unavailable")

    def kimi_runner(
        command: list[str],
        timeout: float,
        cwd: Path,
        stdin: str,
        env: dict[str, str],
    ) -> CompletedProcess[str]:
        captured["command"] = command
        return CompletedProcess(
            command,
            0,
            stdout=json.dumps(payload),
            stderr="",
        )

    provider = _provider()
    assert isinstance(provider, FallbackVisionProvider)
    assert isinstance(provider.fallback, KimiVisionProvider)
    monkeypatch.setattr(provider.primary, "analyze", primary_unavailable)
    provider.fallback.capability_checker = lambda: True
    provider.fallback.runner = kimi_runner

    result = provider.analyze(
        VisionRequest(
            prompt_version="chart-evidence-v1",
            image_paths=[FIXTURE],
            storage_root=FIXTURE.parent,
            privacy_assessment=PrivacyAssessment(
                contains_account_identifiers=False,
                safe_for_model=True,
            ),
        )
    )

    assert result.provider == "kimi"
    assert result.model == "kimi-vision-test"
    assert provider.fallback.isolation_checker() is True
    assert captured["command"][-2:] == ["--model", "kimi-vision-test"]


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
    assert isinstance(provider, FallbackVisionProvider)
    assert isinstance(provider.primary, CodexVisionProvider)
    assert provider.primary.model == "gpt-api-test"
    assert provider.primary.model_provider == "api-provider"


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
