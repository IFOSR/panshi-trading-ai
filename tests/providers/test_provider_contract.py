import json
from hashlib import sha256
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from pydantic import ValidationError

from trading_agent.providers.base import ProviderUnavailable, VisionRequest
from trading_agent.providers.codex import CodexVisionProvider
from trading_agent.providers.codex import ScreenshotExtraction
from trading_agent.providers.fallback import FallbackVisionProvider
from trading_agent.providers.kimi import KimiVisionProvider, configured_kimi_supports_images
from trading_agent.vision.privacy import PrivacyAssessment
from trading_agent.vision.prompts import prompt_sha256, resolve_prompt


FIXTURE = Path("tests/fixtures/charts/daily_boll_macd_volume.png")


def unknown_strategy_facts() -> dict[str, object]:
    return {
        "trend_bias": "UNKNOWN",
        "price_location": "UNKNOWN",
        "volume_state": "UNKNOWN",
        "momentum_state": "UNKNOWN",
        "position_behavior": "UNKNOWN",
        "price_confirmation": None,
        "price_confirmation_direction": "UNKNOWN",
        "price_confirmation_type": "UNKNOWN",
    }


def unknown_strategy_fact_support() -> dict[str, object]:
    return {
        "trend_bias": None,
        "price_location": None,
        "volume_state": None,
        "momentum_state": None,
        "position_behavior": None,
        "price_confirmation": None,
        "price_confirmation_direction": None,
        "price_confirmation_type": None,
    }


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


class FakeAcpClient:
    def __init__(self, output: str) -> None:
        self.output = output
        self.calls: list[tuple[str, list[Path]]] = []

    def complete(self, prompt: str, *, image_paths=()) -> str:
        self.calls.append((prompt, list(image_paths)))
        return self.output


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
    assert "--ignore-user-config" not in command
    assert not any("model_provider=" in item for item in command)
    assert not any("code-cli.cn" in item for item in command)


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
        "strategy_facts": unknown_strategy_facts(),
        "strategy_fact_support": unknown_strategy_fact_support(),
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
    assert evidence.prompt_sha256 == prompt_sha256("chart-evidence-v1")
    assert evidence.image_sha256


def test_codex_rejects_unknown_prompt_version_before_runner() -> None:
    called = False

    def runner(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("runner must not execute for an unknown prompt")

    request = make_request().model_copy(
        update={"prompt_version": "chart-evidence-v999"}
    )

    with pytest.raises(ValueError, match="unknown prompt version"):
        CodexVisionProvider(runner=runner).analyze(request)

    assert called is False


def test_chart_prompt_does_not_block_on_missing_individual_daily_ticks() -> None:
    prompt = resolve_prompt("chart-evidence-v2")

    assert "日线图不要求逐一显示每个交易日的日期刻度" in prompt
    assert "缺少逐日日期刻度本身不得写入 blocking_issues" in prompt
    assert "结构化行情将校验精确截止时间和收盘状态" in prompt


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
        "strategy_facts": unknown_strategy_facts(),
        "strategy_fact_support": unknown_strategy_fact_support(),
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
    provider = KimiVisionProvider(
        client=FakeAcpClient("当前模型不支持图像输入，无法读取和分析该图片。"),
        capability_checker=lambda: True,
    )

    with pytest.raises(ProviderUnavailable, match="image"):
        provider.analyze(
            make_request()
        )


def test_codex_runs_in_isolated_directory_with_rules_disabled(
    tmp_path: Path,
) -> None:
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
        "strategy_facts": unknown_strategy_facts(),
        "strategy_fact_support": unknown_strategy_fact_support(),
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
        captured.update(
            command=command,
            cwd=cwd,
            stdin=stdin,
            env=env,
            config=(Path(env["CODEX_HOME"]) / "config.toml").read_text(
                encoding="utf-8"
            ),
        )
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return CompletedProcess(command, 0, stdout="", stderr="")

    with pytest.MonkeyPatch.context() as monkeypatch:
        codex_home = tmp_path / "codex-home"
        codex_home.mkdir()
        (codex_home / "config.toml").write_text(
            '\n'.join(
                [
                    'model_provider = "machine-default"',
                    '[model_providers.machine-default]',
                    'env_key = "MACHINE_DEFAULT_API_KEY"',
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("CODEX_HOME", str(codex_home))
        monkeypatch.setenv("MACHINE_DEFAULT_API_KEY", "test-key")
        monkeypatch.setenv("CODE_CLI_API_KEY", "must-not-be-forwarded")
        monkeypatch.setenv("UNRELATED_SECRET", "must-not-be-forwarded")
        evidence = CodexVisionProvider(runner=runner).analyze(
            make_request().model_copy(update={"user_context": "ignored metadata"})
        )

    command = captured["command"]
    assert isinstance(command, list)
    assert "--ignore-user-config" not in command
    assert "--ignore-rules" in command
    assert captured["cwd"] != Path.cwd()
    assert command[-1] == "-"
    assert "中国期货交易截图证据抽取器" in str(captured["stdin"])
    assert evidence.prompt_sha256 == sha256(
        str(captured["stdin"]).encode("utf-8")
    ).hexdigest()
    assert "ignored metadata" not in str(captured["stdin"])
    assert not any("model_provider=" in item for item in command)
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["MACHINE_DEFAULT_API_KEY"] == "test-key"
    assert Path(environment["HOME"]) == captured["cwd"]
    assert Path(environment["TMPDIR"]).parent == captured["cwd"]
    isolated_codex_home = Path(environment["CODEX_HOME"])
    assert isolated_codex_home.parent == captured["cwd"]
    isolated_config = captured["config"]
    assert isinstance(isolated_config, str)
    assert 'default_permissions = "vision-read"' in isolated_config
    assert 'inherit = "none"' in isolated_config
    assert '":workspace_roots" = "read"' in isolated_config
    assert "enabled = false" in isolated_config
    assert "[mcp_servers." not in isolated_config
    assert "--strict-config" in command
    assert "--sandbox" not in command
    assert "CODE_CLI_API_KEY" not in environment
    assert "UNRELATED_SECRET" not in environment


def test_kimi_hashes_the_exact_prompt_passed_to_the_cli() -> None:
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
        "strategy_facts": unknown_strategy_facts(),
        "strategy_fact_support": unknown_strategy_fact_support(),
        "observations": [],
        "blocking_issues": ["CONTRACT_MISSING"],
        "allowed_usage": "QUALITATIVE_ONLY",
    }

    client = FakeAcpClient(json.dumps(payload))

    evidence = KimiVisionProvider(
        model="kimi-k3",
        client=client,
        capability_checker=lambda: True,
    ).analyze(
        make_request().model_copy(update={"user_context": "ignored metadata"})
    )

    prompt, image_paths = client.calls[0]
    assert evidence.prompt_sha256 == sha256(prompt.encode("utf-8")).hexdigest()
    assert "image-0.png" in prompt
    assert str(FIXTURE.resolve()) not in prompt
    assert "ignored metadata" not in prompt
    assert image_paths == [FIXTURE]
    assert evidence.provider == "kimi"
    assert evidence.model == "kimi-k3"


def test_codex_explicit_provider_works_without_machine_config(
    tmp_path: Path,
) -> None:
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
        "strategy_facts": unknown_strategy_facts(),
        "strategy_fact_support": unknown_strategy_fact_support(),
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
        captured.update(
            command=command,
            cwd=cwd,
            env=env,
            config=(Path(env["CODEX_HOME"]) / "config.toml").read_text(
                encoding="utf-8"
            ),
        )
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return CompletedProcess(command, 0, stdout="", stderr="")

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("CODE_CLI_API_KEY", "compose-key")
        monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing-codex-home"))
        provider = CodexVisionProvider(
            model="gpt-5.6-sol",
            model_provider="code-cli",
            provider_base_url="https://provider.example/v1",
            provider_env_key="CODE_CLI_API_KEY",
            runner=runner,
        )
        evidence = provider.analyze(make_request())

    assert evidence.provider == "codex"
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["CODE_CLI_API_KEY"] == "compose-key"
    config = captured["config"]
    assert isinstance(config, str)
    assert 'model_provider = "code-cli"' in config
    assert 'base_url = "https://provider.example/v1"' in config
    assert 'env_key = "CODE_CLI_API_KEY"' in config


def test_codex_explicit_provider_fails_before_runner_when_credential_is_missing(
    monkeypatch,
) -> None:
    called = False

    def runner(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("runner must not execute without provider credential")

    monkeypatch.delenv("PRIVATE_MODEL_KEY", raising=False)
    provider = CodexVisionProvider(
        model_provider="private-provider",
        provider_base_url="https://model.example/v1",
        provider_env_key="PRIVATE_MODEL_KEY",
        runner=runner,
    )

    with pytest.raises(ProviderUnavailable, match="PRIVATE_MODEL_KEY"):
        provider.analyze(make_request())

    assert called is False


def test_codex_provider_override_is_written_to_isolated_config_not_cli(
    tmp_path: Path,
) -> None:
    provider = CodexVisionProvider(
        model="gpt-5.6-sol",
        model_provider="private-provider",
        provider_base_url="https://model.example/v1",
        provider_env_key="PRIVATE_MODEL_KEY",
    )

    command = provider.build_command(
        request=make_request(),
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
    )

    assert not any("model_provider=" in item for item in command)


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


def test_kimi_uses_acp_local_isolation_without_docker_boundary() -> None:
    client = FakeAcpClient(
        json.dumps(
            {
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
                "strategy_facts": unknown_strategy_facts(),
                "strategy_fact_support": unknown_strategy_fact_support(),
                "observations": [],
                "blocking_issues": ["CONTRACT_MISSING"],
                "allowed_usage": "QUALITATIVE_ONLY",
            }
        )
    )

    evidence = KimiVisionProvider(
        model="kimi-k3",
        client=client,
        capability_checker=lambda: True,
    ).analyze(make_request())

    assert evidence.provider == "kimi"
    assert client.calls[0][1] == [FIXTURE]


def test_kimi_capability_check_is_bound_to_the_selected_default_model(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "\n".join(
            [
                'default_model = "text-only"',
                "[models.text-only]",
                'capabilities = ["text_in"]',
                "[models.vision-capable]",
                'capabilities = ["text_in", "image_in"]',
            ]
        ),
        encoding="utf-8",
    )

    assert configured_kimi_supports_images(config_path=config_path) is False


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
        "strategy_facts": unknown_strategy_facts(),
        "strategy_fact_support": unknown_strategy_fact_support(),
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
        "strategy_facts": unknown_strategy_facts(),
        "strategy_fact_support": unknown_strategy_fact_support(),
        "observations": [],
        "blocking_issues": ["BAR_CLOSE_UNKNOWN"],
        "allowed_usage": "QUALITATIVE_ONLY",
    }

    extraction = ScreenshotExtraction.model_validate(payload)

    assert extraction.cutoff_time == "2026-07-20"


def test_visible_intraday_time_without_zone_assumes_china_futures_timezone() -> None:
    payload = {
        "image_role": "EXECUTION_60M",
        "instrument": "棉花",
        "contract": "cf2609",
        "timeframe": "60m",
        "cutoff_time": "2026-07-22 14:59",
        "last_bar_closed": True,
        "indicators": {
            "boll": None,
            "macd": None,
            "volume": None,
            "position_behavior": None,
            "notes": [],
        },
        "strategy_facts": unknown_strategy_facts(),
        "strategy_fact_support": unknown_strategy_fact_support(),
        "observations": [],
        "blocking_issues": [],
        "allowed_usage": "QUALITATIVE_ONLY",
    }

    extraction = ScreenshotExtraction.model_validate(payload)

    assert extraction.cutoff_time == "2026-07-22T14:59:00+08:00"
