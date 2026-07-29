import pytest

from trading_agent.strategies.contracts import StrategyManifest
from trading_agent.strategies.registry import (
    StrategyNotFound,
    StrategyRegistry,
    configured_strategy_registry,
)


class FakeStrategy:
    def __init__(self, version: str) -> None:
        self.manifest = StrategyManifest(
            strategy_id="fixture",
            display_name="Fixture",
            version=version,
            status="test",
            entrypoint="fixtures:FakeStrategy",
            supported_markets=["CN_FUTURES"],
            supported_timeframes=["1d"],
            process_label="Fixture Process",
            risk_profile_id="risk-v1",
        )

    def evaluate(self, snapshot):
        raise AssertionError("registry tests do not execute strategies")


def test_registry_resolves_latest_version_and_exact_version() -> None:
    registry = StrategyRegistry(default_strategy_id="fixture")
    v1 = FakeStrategy("1.0.0")
    v2 = FakeStrategy("1.10.0")
    registry.register(v1)
    registry.register(v2)

    assert registry.resolve("fixture").manifest.version == "1.10.0"
    assert registry.resolve("fixture", "1.0.0") is v1


def test_registry_rejects_duplicate_strategy_versions() -> None:
    registry = StrategyRegistry(default_strategy_id="fixture")
    registry.register(FakeStrategy("1.0.0"))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeStrategy("1.0.0"))


def test_registry_raises_a_typed_error_for_unknown_strategies() -> None:
    registry = StrategyRegistry(default_strategy_id="fixture")

    with pytest.raises(StrategyNotFound, match="missing"):
        registry.resolve("missing")


def test_configured_registry_contains_the_default_structure_strategy() -> None:
    registry = configured_strategy_registry()

    manifest = registry.default().manifest

    assert manifest.strategy_id == "structure_confirmation"
    assert manifest.display_name == "结构确认策略"
    assert manifest.version == "1.0.0"
    assert manifest.process_label == "八步结构确认"
