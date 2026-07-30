from pathlib import Path

import pytest

from trading_agent.agents.models import AgentRuntime
from trading_agent.agents.registry import (
    AgentBackendRegistry,
    AgentBackendUnavailable,
    configured_agent_backend_manifests,
)


class Provider:
    pass


def runtime(backend_id: str, model_id: str) -> AgentRuntime:
    provider = Provider()
    return AgentRuntime(
        backend_id=backend_id,
        model_id=model_id,
        vision=provider,
        clarification=provider,
        conversation=provider,
    )


def test_manifests_default_to_codex_and_kimi_3(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "\n".join(
            [
                'default_model = "kimi-k3"',
                '[models."kimi-k3"]',
                'provider = "managed:kimi-code"',
                'model = "kimi-k3"',
                "max_context_size = 1000000",
                'capabilities = ["image_in", "tool_use"]',
                '[models."kimi-code/kimi-for-coding"]',
                'provider = "managed:kimi-code"',
                'model = "kimi-for-coding"',
                "max_context_size = 262144",
                'capabilities = ["video_in", "tool_use"]',
            ]
        ),
        encoding="utf-8",
    )

    manifests = configured_agent_backend_manifests(
        kimi_config_path=config,
        executable_finder=lambda command: f"/usr/local/bin/{command}",
        kimi_acp_probe=lambda model: (True, None),
    )

    assert [item.backend_id for item in manifests] == ["codex", "kimi"]
    assert manifests[0].default_model_id == "gpt-5.6-sol"
    assert manifests[1].default_model_id == "kimi-k3"
    kimi_models = {item.model_id: item for item in manifests[1].models}
    assert kimi_models["kimi-k3"].available is True
    assert set(kimi_models["kimi-k3"].capabilities) == {
        "vision",
        "clarification",
        "conversation",
    }
    assert kimi_models["kimi-code/kimi-for-coding"].available is False
    assert "image_in" in (kimi_models["kimi-code/kimi-for-coding"].unavailable_reason or "")


def test_kimi_model_is_unavailable_when_acp_initialization_fails(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "\n".join(
            [
                '[models."kimi-k3"]',
                'capabilities = ["image_in", "tool_use"]',
            ]
        ),
        encoding="utf-8",
    )

    manifests = configured_agent_backend_manifests(
        kimi_config_path=config,
        executable_finder=lambda command: f"/usr/local/bin/{command}",
        kimi_acp_probe=lambda model: (False, "Kimi ACP authentication failed"),
    )

    kimi = next(item for item in manifests if item.backend_id == "kimi")
    kimi_3 = next(item for item in kimi.models if item.model_id == "kimi-k3")
    assert kimi_3.available is False
    assert kimi_3.unavailable_reason == "Kimi ACP authentication failed"


def test_kimi_3_is_visible_with_reason_when_not_configured(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        'default_model = "kimi-code/kimi-for-coding"\n',
        encoding="utf-8",
    )

    manifests = configured_agent_backend_manifests(
        kimi_config_path=config,
        executable_finder=lambda command: f"/usr/local/bin/{command}",
    )

    kimi = next(item for item in manifests if item.backend_id == "kimi")
    kimi_3 = next(item for item in kimi.models if item.model_id == "kimi-k3")
    assert kimi_3.available is False
    assert kimi_3.unavailable_reason == "Kimi Code 尚未配置模型 kimi-k3"


def test_registry_never_falls_back_from_unavailable_selection() -> None:
    manifests = configured_agent_backend_manifests(
        kimi_config_path=Path("/missing/config.toml"),
        executable_finder=lambda command: (
            "/usr/local/bin/codex" if command == "codex" else "/usr/local/bin/kimi"
        ),
    )
    registry = AgentBackendRegistry(
        manifests=manifests,
        runtime_factory=runtime,
    )

    selected = registry.resolve("codex", None)
    assert selected.backend_id == "codex"
    assert selected.model_id == "gpt-5.6-sol"

    with pytest.raises(AgentBackendUnavailable, match="kimi-k3"):
        registry.resolve("kimi", "kimi-k3")


def test_registry_rejects_unknown_backend_and_model() -> None:
    registry = AgentBackendRegistry(
        manifests=configured_agent_backend_manifests(
            kimi_config_path=Path("/missing/config.toml"),
            executable_finder=lambda command: f"/usr/local/bin/{command}",
        ),
        runtime_factory=runtime,
    )

    with pytest.raises(ValueError, match="unknown agent backend"):
        registry.resolve("other", None)
    with pytest.raises(ValueError, match="unknown model"):
        registry.resolve("codex", "other")
