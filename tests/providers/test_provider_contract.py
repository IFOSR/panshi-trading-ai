import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from pydantic import ValidationError

from trading_agent.providers.base import ProviderUnavailable, VisionRequest
from trading_agent.providers.codex import CodexVisionProvider
from trading_agent.providers.codex import ScreenshotExtraction
from trading_agent.providers.fallback import FallbackVisionProvider
from trading_agent.providers.kimi import KimiVisionProvider


FIXTURE = Path("tests/fixtures/charts/daily_boll_macd_volume.png")


def test_vision_request_requires_at_least_one_original_image() -> None:
    with pytest.raises(ValidationError):
        VisionRequest(prompt_version="chart-evidence-v1", image_paths=[])


def test_codex_command_attaches_original_image_and_schema(tmp_path: Path) -> None:
    provider = CodexVisionProvider(model="gpt-5.6-sol")
    request = VisionRequest(
        prompt_version="chart-evidence-v1",
        image_paths=[FIXTURE],
    )

    command = provider.build_command(
        request=request,
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
    )

    assert command[:2] == ["codex", "exec"]
    assert "--image" in command
    assert str(FIXTURE) in command
    assert "--output-schema" in command
    assert "gpt-5.6-sol" in command


def test_codex_output_schema_forbids_additional_properties_recursively() -> None:
    schema = ScreenshotExtraction.model_json_schema()

    def assert_closed(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                assert set(node.get("required", [])) == set(node.get("properties", {}))
            for value in node.values():
                assert_closed(value)
        elif isinstance(node, list):
            for value in node:
                assert_closed(value)

    assert_closed(schema)


def test_codex_parses_strict_json_and_adds_provenance() -> None:
    payload = {
        "image_role": "STATE_DAILY",
        "instrument": None,
        "contract": None,
        "timeframe": "1d",
        "cutoff_time": None,
        "last_bar_closed": None,
        "indicators": {
            "boll": {
                "period": 20,
                "mid": 16964.5,
                "upper": 18081.71,
                "lower": 15847.29,
            },
            "macd": None,
            "volume": None,
            "position_behavior": None,
            "notes": [],
        },
        "observations": [],
        "blocking_issues": ["CONTRACT_MISSING"],
        "allowed_usage": "QUALITATIVE_ONLY",
    }

    def runner(command: list[str], timeout: float) -> CompletedProcess[str]:
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return CompletedProcess(command, 0, stdout="", stderr="")

    provider = CodexVisionProvider(model="gpt-5.6-sol", runner=runner)
    evidence = provider.analyze(
        VisionRequest(prompt_version="chart-evidence-v1", image_paths=[FIXTURE])
    )

    assert evidence.timeframe == "1d"
    assert evidence.provider == "codex"
    assert evidence.model == "gpt-5.6-sol"
    assert evidence.image_sha256


def test_codex_downgrades_exact_usage_when_critical_fields_are_missing() -> None:
    payload = {
        "image_role": "STATE_DAILY",
        "instrument": None,
        "contract": None,
        "timeframe": "1d",
        "cutoff_time": "2026/07/20",
        "last_bar_closed": None,
        "indicators": {
            "boll": None,
            "macd": None,
            "volume": None,
            "position_behavior": None,
            "notes": [],
        },
        "observations": [],
        "blocking_issues": ["CONTRACT_MISSING", "BAR_CLOSE_UNKNOWN"],
        "allowed_usage": "EXACT",
    }

    def runner(command: list[str], timeout: float) -> CompletedProcess[str]:
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return CompletedProcess(command, 0, stdout="", stderr="")

    evidence = CodexVisionProvider(runner=runner).analyze(
        VisionRequest(prompt_version="chart-evidence-v1", image_paths=[FIXTURE])
    )

    assert evidence.allowed_usage.value == "QUALITATIVE_ONLY"


def test_fallback_uses_kimi_only_when_codex_is_unavailable() -> None:
    class Primary:
        def analyze(self, request: VisionRequest):
            raise ProviderUnavailable("codex unavailable")

    class Fallback:
        def analyze(self, request: VisionRequest):
            return "kimi-result"

    provider = FallbackVisionProvider(primary=Primary(), fallback=Fallback())

    assert provider.analyze(
        VisionRequest(prompt_version="chart-evidence-v1", image_paths=[FIXTURE])
    ) == "kimi-result"


def test_kimi_rejects_text_only_model_response() -> None:
    def runner(command: list[str], timeout: float) -> CompletedProcess[str]:
        return CompletedProcess(
            command,
            0,
            stdout="当前模型不支持图像输入，无法读取和分析该图片。",
            stderr="",
        )

    provider = KimiVisionProvider(runner=runner)

    with pytest.raises(ProviderUnavailable, match="image"):
        provider.analyze(
            VisionRequest(prompt_version="chart-evidence-v1", image_paths=[FIXTURE])
        )
