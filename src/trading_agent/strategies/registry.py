from collections import defaultdict

from trading_agent.strategies.contracts import StrategyManifest, StrategyPlugin
from trading_agent.strategies.structure_confirmation import (
    StructureConfirmationStrategy,
)


class StrategyNotFound(LookupError):
    pass


def _version_key(version: str) -> tuple[int, int, int]:
    major, minor, patch = version.split(".")
    return int(major), int(minor), int(patch)


class StrategyRegistry:
    def __init__(self, *, default_strategy_id: str) -> None:
        self.default_strategy_id = default_strategy_id
        self._plugins: dict[str, dict[str, StrategyPlugin]] = defaultdict(dict)

    def register(self, plugin: StrategyPlugin) -> None:
        manifest = plugin.manifest
        versions = self._plugins[manifest.strategy_id]
        if manifest.version in versions:
            raise ValueError(
                f"strategy {manifest.strategy_id}@{manifest.version} already registered"
            )
        versions[manifest.version] = plugin

    def resolve(
        self,
        strategy_id: str,
        version: str | None = None,
    ) -> StrategyPlugin:
        versions = self._plugins.get(strategy_id)
        if not versions:
            raise StrategyNotFound(strategy_id)
        eligible = {
            candidate_version: plugin
            for candidate_version, plugin in versions.items()
            if plugin.manifest.status != "disabled"
        }
        if version is None:
            if not eligible:
                raise StrategyNotFound(f"{strategy_id} has no executable version")
            resolved_version = max(eligible, key=_version_key)
        else:
            resolved_version = version
        try:
            plugin = versions[resolved_version]
        except KeyError as exc:
            raise StrategyNotFound(f"{strategy_id}@{resolved_version}") from exc
        if plugin.manifest.status == "disabled":
            raise StrategyNotFound(f"{strategy_id}@{resolved_version} is disabled")
        return plugin

    def default(self) -> StrategyPlugin:
        versions = self._plugins.get(self.default_strategy_id)
        stable = {
            version: plugin
            for version, plugin in (versions or {}).items()
            if plugin.manifest.status == "stable"
        }
        if not stable:
            raise StrategyNotFound(
                f"{self.default_strategy_id} has no stable default version"
            )
        return stable[max(stable, key=_version_key)]

    def manifests(self) -> list[StrategyManifest]:
        return [
            plugin.manifest
            for strategy_id in sorted(self._plugins)
            for _, plugin in sorted(
                self._plugins[strategy_id].items(),
                key=lambda item: _version_key(item[0]),
                reverse=True,
            )
        ]


def configured_strategy_registry() -> StrategyRegistry:
    registry = StrategyRegistry(default_strategy_id="structure_confirmation")
    registry.register(StructureConfirmationStrategy())
    return registry
