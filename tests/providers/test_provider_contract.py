import json
from pathlib import Path
from typing import Callable

import pytest
from pydantic import ValidationError

from trading_agent.providers.base import (
    ProviderResponseError,
    ProviderUnavailable,
    VisionRequest,
)
from trading_agent.providers.deepseek import (
    DEFAULT_MODEL,
    _HttpRunner,
    DeepSeekVisionProvider,
)
from trading_agent.providers.extraction import ScreenshotExtraction
from trading_agent.providers.fallback import FallbackVisionProvider
from trading_agent.providers import kimi
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


def make_payload(**overrides) -> dict[str, object]:
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
    payload.update(overrides)
    return payload


def json_runner(payload: dict[str, object]) -> _HttpRunner:
    def complete(
        messages: list[dict],
        *,
        model: str = DEFAULT_MODEL,
        temperature: float = 0.0,
    ) -> str:
        return json.dumps(payload, ensure_ascii=False)

    runner = _HttpRunner()
    runner.complete = complete  # type: ignore[method-assign]
    return runner


def test_vision_request_requires_at_least_one_original_image() -> None:
    with pytest.raises(ValidationError):
        VisionRequest(prompt_version="chart-evidence-v1", image_paths=[])


def test_deepseek_output_schema_forbids_additional_properties_recursively() -> None:
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


def test_deepseek_parses_strict_json_and_adds_provenance() -> None:
    provider = DeepSeekVisionProvider(
        model="deepseek-chat",
        runner=json_runner(make_payload()),
    )
    evidence = provider.analyze(make_request())

    assert evidence.timeframe == "1d"
    assert evidence.provider == "deepseek"
    assert evidence.model == "deepseek-chat"
    assert evidence.prompt_sha256 == prompt_sha256("chart-evidence-v1")
    assert evidence.image_sha256


def test_deepseek_rejects_unknown_prompt_version_before_runner() -> None:
    called = False

    def runner(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("runner must not execute for an unknown prompt")

    request = make_request().model_copy(
        update={"prompt_version": "chart-evidence-v999"}
    )

    with pytest.raises(ValueError, match="unknown prompt version"):
        DeepSeekVisionProvider(runner=runner).analyze(request)

    assert called is False


def test_chart_prompt_does_not_block_on_missing_individual_daily_ticks() -> None:
    prompt = resolve_prompt("chart-evidence-v2")

    assert "日线图不要求逐一显示每个交易日的日期刻度" in prompt
    assert "缺少逐日日期刻度本身不得写入 blocking_issues" in prompt
    assert "结构化行情将校验精确截止时间和收盘状态" in prompt


def test_deepseek_downgrades_exact_usage_when_critical_fields_are_missing() -> None:
    payload = make_payload(
        cutoff_time="2026-07-20T15:00:00+08:00",
        indicators={
            "boll": None,
            "macd": None,
            "volume": None,
            "position_behavior": None,
            "notes": [],
        },
        blocking_issues=["CONTRACT_MISSING", "BAR_CLOSE_UNKNOWN"],
        allowed_usage="EXACT",
    )

    def runner(*args, **kwargs):
        raise AssertionError("unexpected")

    provider = DeepSeekVisionProvider(
        runner=json_runner(payload),
    )
    evidence = provider.analyze(make_request())

    assert evidence.allowed_usage == "QUALITATIVE_ONLY"


def test_deepseek_fails_before_runner_when_credential_is_missing(
    monkeypatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    provider = DeepSeekVisionProvider()

    with pytest.raises(ProviderUnavailable, match="DEEPSEEK_API_KEY"):
        provider.analyze(make_request())


def test_fallback_uses_kimi_only_when_deepseek_is_unavailable() -> None:
    requests: list[VisionRequest] = []

    class Primary:
        def analyze(self, request: VisionRequest):
            requests.append(request)
            raise ProviderUnavailable("deepseek unavailable")

    class Fallback:
        def analyze(self, request: VisionRequest):
            requests.append(request)
            return "kimi-result"

    fallback = FallbackVisionProvider(
        primary=Primary(),  # type: ignore[arg-type]
        fallback=Fallback(),  # type: ignore[arg-type]
    )

    result = fallback.analyze(make_request())

    assert result == "kimi-result"
    assert len(requests) == 2


def test_kimi_rejects_text_only_model_response() -> None:
    text_response = "抱歉，当前模型无法读取和分析该图片"

    def runner(
        command: list[str],
        timeout: float,
        cwd: Path,
        stdin: str,
        env: dict[str, str],
    ):
        return type(
            "Result",
            (),
            {
                "returncode": 0,
                "stdout": text_response,
                "stderr": "",
            },
        )()

    provider = KimiVisionProvider(
        model="kimi-latest",
        runner=runner,
        capability_checker=lambda: True,
        isolation_checker=lambda: True,
    )

    with pytest.raises(ProviderUnavailable, match="does not support image"):
        provider.analyze(make_request())


def test_kimi_hashes_the_exact_prompt_passed_to_the_cli() -> None:
    captured: dict[str, object] = {}

    def runner(
        command: list[str],
        timeout: float,
        cwd: Path,
        stdin: str,
        env: dict[str, str],
    ):
        captured["stdin"] = stdin
        return type(
            "Result",
            (),
            {
                "returncode": 1,
                "stdout": "",
                "stderr": "failed",
            },
        )()

    provider = KimiVisionProvider(
        model="kimi-latest",
        runner=runner,
        capability_checker=lambda: True,
        isolation_checker=lambda: True,
    )

    with pytest.raises(ProviderUnavailable):
        provider.analyze(make_request())

    expected_hash = kimi.provider_prompt_sha256(
        "chart-evidence-v1",
        provider="kimi",
        image_suffixes=[".png"],
    )
    assert kimi.provider_prompt_sha256(
        "chart-evidence-v1",
        provider="kimi",
        image_suffixes=[".png"],
    ) == expected_hash


def test_unsafe_privacy_assessment_blocks_provider_before_runner() -> None:
    called = False

    def runner(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("runner must not execute for unsafe privacy")

    request = make_request().model_copy(
        update={
            "privacy_assessment": PrivacyAssessment(
                contains_account_identifiers=True,
                safe_for_model=False,
            )
        }
    )

    with pytest.raises(ValueError, match="privacy assessment"):
        DeepSeekVisionProvider(runner=runner).analyze(request)

    assert called is False


def test_kimi_without_verified_image_capability_is_unavailable() -> None:
    provider = KimiVisionProvider(
        capability_checker=lambda: False,
        isolation_checker=lambda: True,
    )

    with pytest.raises(ProviderUnavailable, match="no verified image capability"):
        provider.analyze(make_request())


def test_kimi_requires_a_verified_tool_isolation_boundary() -> None:
    provider = KimiVisionProvider(
        capability_checker=lambda: True,
        isolation_checker=lambda: False,
    )

    with pytest.raises(ProviderUnavailable, match="isolation"):
        provider.analyze(make_request())


def test_kimi_external_isolation_checker_fails_closed() -> None:
    checker = kimi.trusted_external_isolation_checker(
        verified=False,
        provider="container",
    )
    assert checker() is False


def test_kimi_external_isolation_checker_accepts_trusted_os_boundary() -> None:
    checker = kimi.trusted_external_isolation_checker(
        verified=True,
        provider="firejail",
    )
    assert checker() is True


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
    payload = make_payload(allowed_usage="EXACT")

    provider = DeepSeekVisionProvider(
        runner=json_runner(payload),
    )
    evidence = provider.analyze(make_request())

    assert evidence.allowed_usage == "QUALITATIVE_ONLY"


def test_observation_requires_valid_source_image_index() -> None:
    payload = make_payload(
        observations=[
            {
                "evidence_id": "obs-1",
                "kind": "PRICE",
                "conclusion": "价格 3550",
                "confidence": 0.9,
                "visible_text": None,
                "evidence_description": "可见价格",
                "source_image_index": 5,
            }
        ],
    )

    provider = DeepSeekVisionProvider(
        runner=json_runner(payload),
    )

    with pytest.raises(ProviderResponseError):
        provider.analyze(make_request())


def test_extraction_rejects_non_finite_indicator_values() -> None:
    payload = make_payload(
        indicators={
            "boll": {"period": 20, "mid": float("nan"), "upper": 1, "lower": -1},
            "macd": None,
            "volume": None,
            "position_behavior": None,
            "notes": [],
        },
    )

    with pytest.raises(ValidationError):
        ScreenshotExtraction.model_validate(payload)


def test_visible_calendar_date_is_normalized_without_inventing_time() -> None:
    extraction = ScreenshotExtraction.model_validate(
        make_payload(cutoff_time="2026/07/20")
    )
    assert extraction.cutoff_time == "2026-07-20"


def test_visible_intraday_time_without_zone_assumes_china_futures_timezone() -> None:
    extraction = ScreenshotExtraction.model_validate(
        make_payload(cutoff_time="2026-07-20T14:30:00")
    )
    assert extraction.cutoff_time == "2026-07-20T14:30:00+08:00"
