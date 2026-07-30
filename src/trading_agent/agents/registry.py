from collections.abc import Callable
from pathlib import Path
import shutil

try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib

from trading_agent.agents.models import (
    AgentBackendManifest,
    AgentModelManifest,
    AgentRuntime,
)
from trading_agent.providers.base import ProviderUnavailable
from trading_agent.providers.kimi_acp import KimiAcpClient


class AgentBackendUnavailable(RuntimeError):
    pass


RuntimeFactory = Callable[[str, str], AgentRuntime]
ExecutableFinder = Callable[[str], str | None]
KimiAcpProbe = Callable[[str], tuple[bool, str | None]]
FULL_CAPABILITIES = ["vision", "clarification", "conversation"]


def _probe_kimi_acp(model_id: str) -> tuple[bool, str | None]:
    try:
        KimiAcpClient(model=model_id, timeout_seconds=10).probe()
    except ProviderUnavailable as exc:
        return False, str(exc)
    return True, None


def _kimi_models(config_path: Path) -> dict[str, set[str]]:
    if not config_path.is_file():
        return {}
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    configured = payload.get("models")
    if not isinstance(configured, dict):
        return {}
    results: dict[str, set[str]] = {}
    for model_id, value in configured.items():
        if not isinstance(model_id, str) or not isinstance(value, dict):
            continue
        capabilities = value.get("capabilities")
        if not isinstance(capabilities, list):
            capabilities = []
        results[model_id] = {
            item for item in capabilities if isinstance(item, str)
        }
    return results


def _kimi_model_manifest(
    *,
    model_id: str,
    display_name: str,
    configured: dict[str, set[str]],
    kimi_executable: str | None,
    kimi_acp_probe: KimiAcpProbe,
) -> AgentModelManifest:
    reason: str | None = None
    if not kimi_executable:
        reason = "Kimi Code CLI 不可用"
    elif model_id not in configured:
        reason = f"Kimi Code 尚未配置模型 {model_id}"
    elif "image_in" not in configured[model_id]:
        reason = f"模型 {model_id} 未声明 image_in 图片能力"
    else:
        available, probe_reason = kimi_acp_probe(model_id)
        if not available:
            reason = probe_reason or "Kimi ACP 初始化失败"
    return AgentModelManifest(
        model_id=model_id,
        display_name=display_name,
        capabilities=FULL_CAPABILITIES,
        available=reason is None,
        unavailable_reason=reason,
    )


def configured_agent_backend_manifests(
    *,
    codex_model: str = "gpt-5.6-sol",
    kimi_config_path: Path | None = None,
    executable_finder: ExecutableFinder = shutil.which,
    kimi_acp_probe: KimiAcpProbe = _probe_kimi_acp,
) -> list[AgentBackendManifest]:
    codex_executable = executable_finder("codex")
    codex_reason = None if codex_executable else "Codex CLI 不可用"
    codex_model_manifest = AgentModelManifest(
        model_id=codex_model,
        display_name="GPT-5.6",
        capabilities=FULL_CAPABILITIES,
        available=codex_reason is None,
        unavailable_reason=codex_reason,
    )

    config_path = kimi_config_path or Path.home() / ".kimi-code" / "config.toml"
    configured = _kimi_models(config_path)
    kimi_executable = executable_finder("kimi")
    kimi_models = [
        _kimi_model_manifest(
            model_id="kimi-k3",
            display_name="Kimi 3",
            configured=configured,
            kimi_executable=kimi_executable,
            kimi_acp_probe=kimi_acp_probe,
        ),
        _kimi_model_manifest(
            model_id="kimi-code/kimi-for-coding",
            display_name="Kimi for Coding",
            configured=configured,
            kimi_executable=kimi_executable,
            kimi_acp_probe=kimi_acp_probe,
        ),
    ]
    available_kimi = [item for item in kimi_models if item.available]
    kimi_reason = (
        None
        if available_kimi
        else kimi_models[0].unavailable_reason or "Kimi Code 当前不可用"
    )
    return [
        AgentBackendManifest(
            backend_id="codex",
            display_name="Codex",
            default_model_id=codex_model,
            capabilities=FULL_CAPABILITIES,
            available=codex_model_manifest.available,
            unavailable_reason=codex_reason,
            models=[codex_model_manifest],
        ),
        AgentBackendManifest(
            backend_id="kimi",
            display_name="Kimi Code",
            default_model_id="kimi-k3",
            capabilities=FULL_CAPABILITIES,
            available=bool(available_kimi),
            unavailable_reason=kimi_reason,
            models=kimi_models,
        ),
    ]


class AgentBackendRegistry:
    def __init__(
        self,
        *,
        manifests: list[AgentBackendManifest],
        runtime_factory: RuntimeFactory,
    ) -> None:
        self._manifests = {item.backend_id: item for item in manifests}
        self._runtime_factory = runtime_factory

    def manifests(self) -> list[AgentBackendManifest]:
        return list(self._manifests.values())

    def manifest(self, backend_id: str) -> AgentBackendManifest:
        try:
            return self._manifests[backend_id]
        except KeyError as exc:
            raise ValueError(f"unknown agent backend: {backend_id}") from exc

    def resolve(
        self,
        backend_id: str,
        model_id: str | None,
    ) -> AgentRuntime:
        backend = self.manifest(backend_id)
        selected_model_id = model_id or backend.default_model_id
        model = next(
            (
                candidate
                for candidate in backend.models
                if candidate.model_id == selected_model_id
            ),
            None,
        )
        if model is None:
            raise ValueError(
                f"unknown model for agent backend {backend_id}: {selected_model_id}"
            )
        if not model.available:
            raise AgentBackendUnavailable(
                model.unavailable_reason
                or f"agent backend model unavailable: {backend_id}/{selected_model_id}"
            )
        return self._runtime_factory(backend_id, selected_model_id)
