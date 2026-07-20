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
from trading_agent.vision.privacy import PrivacyAssessment


FIXTURE = Path("tests/fixtures/charts/daily_boll_macd_volume.png")


def make_request() -> VisionRequest:
    return VisionRequest(
        prompt_version="chart-evidence-v1",
        image_paths=[FIXTURE],
        storage_root=FIXTURE.parent,
        privacy_assessment=PrivacyAssessment(
            contains_account_identifiers=False,
            safe_for_model=True,
        ),
    )


def test_vision_request_requires_at_least_one_original_image() -> None:
    with pytest.raises(ValidationError):
        VisionRequest(prompt_version="chart-evidence-v1", image_paths=[])


def test_codex_command_attaches_original_image_and_schema(tmp_path: Path) -> None:
    provider = CodexVisionProvider(model="gpt-5.6-sol")
    request = make_request()

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

    def runner(
        command: list[str],
        timeout: float,
        cwd: Path,
        stdin: str,
        env: dict[str, str],
    ) -> CompletedProcess[str]:
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return CompletedProcess(command, 0, stdout="", stderr="")

    provider = CodexVisionProvider(model="gpt-5.6-sol", runner=runner)
    evidence = provider.analyze(
        make_request()
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
        "cutoff_time": "2026-07-20T15:00:00+08:00",
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

    def runner(
        command: list[str],
        timeout: float,
        cwd: Path,
        stdin: str,
        env: dict[str, str],
    ) -> CompletedProcess[str]:
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return CompletedProcess(command, 0, stdout="", stderr="")

    evidence = CodexVisionProvider(runner=runner).analyze(
        make_request()
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
        make_request()
    ) == "kimi-result"


def test_kimi_rejects_text_only_model_response() -> None:
    def runner(
        command: list[str],
        timeout: float,
        cwd: Path,
        stdin: str,
        env: dict[str, str],
    ) -> CompletedProcess[str]:
        return CompletedProcess(
            command,
            0,
            stdout="当前模型不支持图像输入，无法读取和分析该图片。",
            stderr="",
        )

    provider = KimiVisionProvider(runner=runner, capability_checker=lambda: True)

    with pytest.raises(ProviderUnavailable, match="image"):
        provider.analyze(
            make_request()
        )


def test_codex_runs_in_isolated_directory_with_rules_disabled() -> None:
    captured: dict[str, object] = {}
    payload = {
        "image_role": "STATE_DAILY",
        "instrument": None,
        "contract": None,
        "timeframe": "D1",
        "cutoff_time": None,
        "last_bar_closed": None,
        "indicators": {
            "boll": None,
            "macd": None,
            "volume": None,
            "position_behavior": None,
            "notes": [],
        },
        "observations": [],
        "blocking_issues": ["CONTRACT_MISSING"],
        "allowed_usage": "QUALITATIVE_ONLY",
    }

    def runner(
        command: list[str],
        timeout: float,
        cwd: Path,
        stdin: str,
        env: dict[str, str],
    ) -> CompletedProcess[str]:
        captured.update(command=command, cwd=cwd, stdin=stdin, env=env)
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return CompletedProcess(command, 0, stdout="", stderr="")

    CodexVisionProvider(runner=runner).analyze(make_request())

    command = captured["command"]
    assert isinstance(command, list)
    assert "--ignore-user-config" in command
    assert "--ignore-rules" in command
    assert captured["cwd"] != Path.cwd()
    assert command[-1] == "-"
    assert "中国期货交易截图证据抽取器" in str(captured["stdin"])
    assert 'model_provider="code-cli"' in command
    assert "CODE_CLI_API_KEY" in captured["env"]


def test_unsafe_privacy_assessment_blocks_provider_before_runner() -> None:
    called = False

    def runner(
        command: list[str],
        timeout: float,
        cwd: Path,
        stdin: str,
        env: dict[str, str],
    ) -> CompletedProcess[str]:
        nonlocal called
        called = True
        return CompletedProcess(command, 0, stdout="", stderr="")

    request = VisionRequest(
        prompt_version="chart-evidence-v1",
        image_paths=[FIXTURE],
        storage_root=FIXTURE.parent,
        privacy_assessment=PrivacyAssessment(
            contains_account_identifiers=True,
            sensitive_fields=["account_id"],
            safe_for_model=False,
        ),
    )

    with pytest.raises(ValueError, match="privacy"):
        CodexVisionProvider(runner=runner).analyze(request)

    assert called is False


def test_kimi_without_verified_image_capability_is_unavailable() -> None:
    provider = KimiVisionProvider(capability_checker=lambda: False)

    with pytest.raises(ProviderUnavailable, match="image capability"):
        provider.analyze(make_request())


def test_model_output_cannot_grant_exact_usage() -> None:
    payload = {
        "image_role": "STATE_DAILY",
        "instrument": "螺纹钢",
        "contract": "rb2610",
        "timeframe": "1d",
        "cutoff_time": "2026-07-20T15:00:00+08:00",
        "last_bar_closed": True,
        "indicators": {
            "boll": None,
            "macd": None,
            "volume": None,
            "position_behavior": None,
            "notes": [],
        },
        "observations": [],
        "blocking_issues": [],
        "allowed_usage": "EXACT",
    }

    extraction = ScreenshotExtraction.model_validate(payload)

    from trading_agent.providers.codex import enforce_safe_usage

    assert enforce_safe_usage(extraction).value == "QUALITATIVE_ONLY"


def test_observation_requires_valid_source_image_index() -> None:
    payload = {
        "evidence_id": "ev-1",
        "kind": "PRICE_BELOW_BOLL_MID",
        "conclusion": "true",
        "confidence": 0.9,
        "visible_text": None,
        "evidence_description": "价格位于中轨下方",
        "source_image_index": -1,
    }

    from trading_agent.providers.codex import ObservationExtraction

    with pytest.raises(ValidationError):
        ObservationExtraction.model_validate(payload)


def test_extraction_rejects_non_finite_indicator_values() -> None:
    payload = {
        "period": 20,
        "mid": float("nan"),
        "upper": 18000.0,
        "lower": 16000.0,
    }

    from trading_agent.providers.codex import BollExtraction

    with pytest.raises(ValidationError):
        BollExtraction.model_validate(payload)


def test_visible_calendar_date_is_normalized_without_inventing_time() -> None:
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
        "blocking_issues": ["BAR_CLOSE_UNKNOWN"],
        "allowed_usage": "QUALITATIVE_ONLY",
    }

    extraction = ScreenshotExtraction.model_validate(payload)

    assert extraction.cutoff_time == "2026-07-20"
