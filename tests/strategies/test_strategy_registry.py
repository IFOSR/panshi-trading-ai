import pytest

from trading_agent.strategies.contracts import StrategyManifest
from trading_agent.strategies.registry import StrategyNotFound, StrategyRegistry
from trading_agent.strategies.structure_confirmation import (
    StructureConfirmationStrategy,
)


class VersionedStrategy(StructureConfirmationStrategy):
    def __init__(self, version: str, status: str) -> None:
        self.manifest = StrategyManifest(
            **{
                **StructureConfirmationStrategy.manifest.model_dump(),
                "version": version,
                "status": status,
            }
        )


def test_default_strategy_uses_highest_stable_version() -> None:
    registry = StrategyRegistry(default_strategy_id="structure_confirmation")
    registry.register(VersionedStrategy("1.0.0", "stable"))
    registry.register(VersionedStrategy("1.1.0", "test"))
    registry.register(VersionedStrategy("2.0.0", "disabled"))

    assert registry.default().manifest.version == "1.0.0"


def test_disabled_strategy_cannot_be_resolved_for_execution() -> None:
    registry = StrategyRegistry(default_strategy_id="structure_confirmation")
    registry.register(VersionedStrategy("1.0.0", "stable"))
    registry.register(VersionedStrategy("2.0.0", "disabled"))

    with pytest.raises(StrategyNotFound, match="disabled"):
        registry.resolve("structure_confirmation", "2.0.0")
