from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.run_vision_eval import (
    evaluate_vision_dataset,
    evaluate_vision_records,
    execute_vision_provider,
)
from trading_agent.vision.prompts import prompt_sha256, resolve_prompt


def vision_records() -> list[dict[str, object]]:
    return [
        {
            "labels": {
                "critical_metadata": {"instrument": "AU", "contract": "AU2612"},
                "visible_numbers": {"last_price": "500.0", "volume": "1200"},
                "screenshot_role": "STATE_DAILY",
                "change": "NEW",
                "market_state": "T+",
                "signal_transition": "WATCH_TO_ENTRY",
                "triggers": ["close_above_500"],
                "invalidations": ["close_below_490"],
                "allowed_actions": ["ENTER_CONDITIONAL"],
            },
            "prediction": {
                "accepted": True,
                "critical_metadata": {"instrument": "AU", "contract": None},
                "visible_numbers": {
                    "last_price": "500.0",
                    "volume": "1201",
                    "target": "520",
                },
                "screenshot_role": "STATE_DAILY",
                "change": "NEW",
                "market_state": "T+",
                "signal_transition": "WATCH_TO_ENTRY",
                "triggers": ["close_above_500"],
                "invalidations": [],
                "action": "ENTER_CONDITIONAL",
                "confidence": 0.8,
                "critical_safety_violations": [],
            },
            "latency_seconds": 1.0,
            "cost": 0.1,
        },
        {
            "labels": {
                "critical_metadata": {"instrument": "RB", "contract": "RB2610"},
                "visible_numbers": {"last_price": "3500"},
                "screenshot_role": "STATE_DAILY",
                "change": "UNCHANGED",
                "market_state": "T-",
                "signal_transition": "ENTRY_TO_HOLD",
                "triggers": ["close_below_3490"],
                "invalidations": [],
                "allowed_actions": ["EXIT"],
            },
            "prediction": {
                "accepted": True,
                "critical_metadata": {"instrument": "RB", "contract": "RB2605"},
                "visible_numbers": {"last_price": "3500"},
                "screenshot_role": "EXECUTION_60M",
                "change": "NEW",
                "market_state": "R",
                "signal_transition": "ENTRY_TO_HOLD",
                "triggers": ["close_below_3490"],
                "invalidations": [],
                "action": "HOLD",
                "confidence": 0.6,
                "critical_safety_violations": [],
            },
            "latency_seconds": 2.0,
            "cost": 0.2,
        },
        {
            "labels": {
                "critical_metadata": {"instrument": "IF"},
                "visible_numbers": {"last_price": "4100"},
                "screenshot_role": "EXECUTION_60M",
                "change": "NEW",
                "market_state": "R",
                "signal_transition": "HOLD_TO_EXIT",
                "triggers": [],
                "invalidations": [],
                "allowed_actions": ["WAIT_FOR_SETUP", "ENTER_CONDITIONAL"],
            },
            "prediction": {
                "accepted": False,
                "critical_metadata": {"instrument": "IF"},
                "visible_numbers": {},
                "screenshot_role": "EXECUTION_60M",
                "change": "NEW",
                "market_state": "R",
                "signal_transition": "WATCH_TO_ENTRY",
                "triggers": [],
                "invalidations": [],
                "action": "WAIT_FOR_SETUP",
                "confidence": 0.9,
                "critical_safety_violations": ["UNCLOSED_BAR_USED"],
            },
            "latency_seconds": 10.0,
            "cost": 0.3,
        },
    ]


def test_evaluate_vision_records_computes_documented_metrics() -> None:
    metrics = evaluate_vision_records(vision_records())

    assert metrics["critical_metadata_precision"] == pytest.approx(3 / 4)
    assert metrics["critical_metadata_coverage"] == pytest.approx(4 / 5)
    assert metrics["visible_number_exact_match"] == pytest.approx(2 / 4)
    assert metrics["screenshot_role_macro_f1"] == pytest.approx(2 / 3)
    assert metrics["change_macro_f1"] == pytest.approx(0.4)
    assert metrics["market_state_macro_f1"] == pytest.approx(5 / 9)
    assert metrics["signal_transition_accuracy"] == pytest.approx(2 / 3)
    assert metrics["trigger_invalidation_coverage"] == pytest.approx(2 / 3)
    assert metrics["expected_calibration_error"] == pytest.approx(0.3)
    assert metrics["unsupported_exact_numbers"] == 1
    assert metrics["critical_safety_violations"] == 1
    assert metrics["strategy_action_contradictions"] == 1
    assert metrics["p50_latency_seconds"] == 2.0
    assert metrics["p95_latency_seconds"] == 10.0
    assert metrics["total_cost"] == pytest.approx(0.6)
    assert metrics["mean_cost_per_analysis"] == pytest.approx(0.2)
    assert metrics["cost_per_accepted_analysis"] == pytest.approx(0.3)


def test_prompt_registry_binds_versions_to_distinct_immutable_content() -> None:
    assert resolve_prompt("chart-evidence-v1") != resolve_prompt("chart-evidence-v2")
    assert prompt_sha256("chart-evidence-v1") != prompt_sha256("chart-evidence-v2")

    with pytest.raises(ValueError, match="unknown prompt version"):
        resolve_prompt("chart-evidence-v999")


def test_evidence_only_execution_does_not_create_strategy_contradictions() -> None:
    record = vision_records()[0]
    prediction = record["prediction"]
    assert isinstance(prediction, dict)
    prediction = {
        key: value
        for key, value in prediction.items()
        if key not in {"action", "triggers", "invalidations", "signal_transition"}
    }

    metrics = evaluate_vision_records(
        [
            {
                **record,
                "prediction": prediction,
            }
        ]
    )

    assert metrics["strategy_action_contradictions"] == 0
    assert "signal_transition_accuracy" not in metrics
    assert "trigger_invalidation_coverage" not in metrics


def dataset_record(
    image_path: Path,
    *,
    split: str = "test",
    dataset_version: str = "vision-benchmark-v1",
    previous_image_path: Path | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "record_id": image_path.stem,
        "dataset_version": dataset_version,
        "image_path": str(image_path),
        "split": split,
        "labels": vision_records()[0]["labels"],
    }
    if previous_image_path is not None:
        record["previous_image_path"] = str(previous_image_path)
    return record


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def successful_execution() -> dict[str, object]:
    labels = vision_records()[0]["labels"]
    assert isinstance(labels, dict)
    return {
        "prediction": {
            "accepted": True,
            "critical_metadata": labels["critical_metadata"],
            "visible_numbers": labels["visible_numbers"],
            "screenshot_role": labels["screenshot_role"],
            "change": labels["change"],
            "market_state": labels["market_state"],
            "signal_transition": labels["signal_transition"],
            "triggers": labels["triggers"],
            "invalidations": labels["invalidations"],
            "action": "ENTER_CONDITIONAL",
            "confidence": 1.0,
            "critical_safety_violations": [],
        },
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "prompt_version": "chart-evidence-v2",
        "prompt_sha256": prompt_sha256("chart-evidence-v2"),
        "latency_seconds": 1.0,
        "cost": 0.1,
    }


def test_prefilled_prediction_is_rejected_instead_of_being_scored(tmp_path: Path) -> None:
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(b"original-image")
    record = dataset_record(image_path)
    record["prediction"] = successful_execution()["prediction"]
    dataset_path = tmp_path / "vision.jsonl"
    write_jsonl(dataset_path, [record])

    with pytest.raises(ValueError, match="prediction"):
        evaluate_vision_dataset(
            dataset_path,
            provider="codex",
            model="gpt-5.6-sol",
            prompt_version="chart-evidence-v2",
            dataset_version="vision-benchmark-v1",
            minimum_samples=1,
            executor=None,
        )


def test_original_image_is_executed_with_requested_provider_model_and_prompt(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "chart.png"
    original = b"original-image-bytes"
    image_path.write_bytes(original)
    dataset_path = tmp_path / "vision.jsonl"
    write_jsonl(dataset_path, [dataset_record(image_path)])
    calls: list[tuple[Path, str, str, str, bytes]] = []

    def executor(
        path: Path,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> dict[str, object]:
        calls.append((path, provider, model, prompt_version, path.read_bytes()))
        return successful_execution()

    metrics = evaluate_vision_dataset(
        dataset_path,
        provider="codex",
        model="gpt-5.6-sol",
        prompt_version="chart-evidence-v2",
        dataset_version="vision-benchmark-v1",
        minimum_samples=1,
        executor=executor,
    )

    assert calls == [
        (
            image_path.resolve(),
            "codex",
            "gpt-5.6-sol",
            "chart-evidence-v2",
            original,
        )
    ]
    assert metrics["critical_metadata_precision"] == 1.0


def test_change_detection_executes_both_original_images(tmp_path: Path) -> None:
    previous_path = tmp_path / "previous.png"
    current_path = tmp_path / "current.png"
    previous_path.write_bytes(b"previous-original")
    current_path.write_bytes(b"current-original")
    record = dataset_record(
        current_path,
        previous_image_path=previous_path,
    )
    labels = record["labels"]
    assert isinstance(labels, dict)
    labels["change"] = "CHANGED"
    dataset_path = tmp_path / "vision.jsonl"
    write_jsonl(dataset_path, [record])
    calls: list[Path] = []

    def executor(path: Path, *_: str) -> dict[str, object]:
        calls.append(path)
        execution = successful_execution()
        prediction = execution["prediction"]
        assert isinstance(prediction, dict)
        prediction["visible_numbers"] = {"hash": path.read_bytes().decode()}
        return execution

    metrics = evaluate_vision_dataset(
        dataset_path,
        provider="codex",
        model="gpt-5.6-sol",
        prompt_version="chart-evidence-v2",
        dataset_version="vision-benchmark-v1",
        minimum_samples=1,
        executor=executor,
    )

    assert calls == [previous_path.resolve(), current_path.resolve()]
    assert metrics["change_macro_f1"] == 1.0


def test_vision_evaluation_rejects_non_test_split(tmp_path: Path) -> None:
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(b"original-image")
    dataset_path = tmp_path / "vision.jsonl"
    write_jsonl(dataset_path, [dataset_record(image_path, split="validation")])

    with pytest.raises(ValueError, match="test split"):
        evaluate_vision_dataset(
            dataset_path,
            provider="codex",
            model="gpt-5.6-sol",
            prompt_version="chart-evidence-v2",
            dataset_version="vision-benchmark-v1",
            minimum_samples=1,
            executor=lambda *_: successful_execution(),
        )


def test_vision_evaluation_rejects_execution_version_mismatch(tmp_path: Path) -> None:
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(b"original-image")
    dataset_path = tmp_path / "vision.jsonl"
    write_jsonl(dataset_path, [dataset_record(image_path)])
    mismatched = successful_execution()
    mismatched["model"] = "different-model"

    with pytest.raises(ValueError, match="model"):
        evaluate_vision_dataset(
            dataset_path,
            provider="codex",
            model="gpt-5.6-sol",
            prompt_version="chart-evidence-v2",
            dataset_version="vision-benchmark-v1",
            minimum_samples=1,
            executor=lambda *_: mismatched,
        )


def test_vision_evaluation_rejects_unknown_prompt_before_executor(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(b"original-image")
    dataset_path = tmp_path / "vision.jsonl"
    write_jsonl(dataset_path, [dataset_record(image_path)])
    called = False

    def executor(*args):
        nonlocal called
        called = True
        return successful_execution()

    with pytest.raises(ValueError, match="unknown prompt version"):
        evaluate_vision_dataset(
            dataset_path,
            provider="codex",
            model="gpt-5.6-sol",
            prompt_version="chart-evidence-v999",
            dataset_version="vision-benchmark-v1",
            minimum_samples=1,
            executor=executor,
        )

    assert called is False


def test_vision_evaluation_rejects_prompt_content_hash_mismatch(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(b"original-image")
    dataset_path = tmp_path / "vision.jsonl"
    write_jsonl(dataset_path, [dataset_record(image_path)])
    mismatched = successful_execution()
    mismatched["prompt_sha256"] = "wrong-hash"

    with pytest.raises(ValueError, match="prompt_sha256"):
        evaluate_vision_dataset(
            dataset_path,
            provider="codex",
            model="gpt-5.6-sol",
            prompt_version="chart-evidence-v2",
            dataset_version="vision-benchmark-v1",
            minimum_samples=1,
            executor=lambda *_: mismatched,
        )


def test_vision_evaluation_rejects_duplicate_original_image_hashes(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    first_path.write_bytes(b"same-original-image")
    second_path.write_bytes(b"same-original-image")
    records = [
        dataset_record(first_path),
        {
            **dataset_record(second_path),
            "record_id": "second-record",
        },
    ]
    dataset_path = tmp_path / "vision.jsonl"
    write_jsonl(dataset_path, records)

    with pytest.raises(ValueError, match="duplicate original image"):
        evaluate_vision_dataset(
            dataset_path,
            provider="codex",
            model="gpt-5.6-sol",
            prompt_version="chart-evidence-v2",
            dataset_version="vision-benchmark-v1",
            minimum_samples=2,
            executor=lambda *_: successful_execution(),
        )


def test_vision_execution_uses_the_configured_production_provider_factory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(b"original-image")
    captured: dict[str, object] = {}

    class ConfiguredProvider:
        def analyze(self, request):
            captured["request"] = request
            return type("Evidence", (), {
                "strategy_facts": type("Facts", (), {"trend_bias": "UNKNOWN"})(),
                "observations": [],
                "allowed_usage": type("Usage", (), {"value": "QUALITATIVE_ONLY"})(),
                "instrument": None,
                "contract": None,
                "timeframe": None,
                "cutoff_time": None,
                "last_bar_closed": None,
                "indicators": {},
                "image_role": "AUXILIARY",
                "provider": "codex",
                "model": "gpt-eval",
                "prompt_version": "chart-evidence-v2",
                "prompt_sha256": prompt_sha256("chart-evidence-v2"),
            })()

    def factory(provider: str, *, model: str):
        captured["factory"] = (provider, model)
        return ConfiguredProvider()

    monkeypatch.setattr(
        "trading_agent.providers.factory.configured_vision_provider",
        factory,
    )

    execution = execute_vision_provider(
        image_path,
        "codex",
        "gpt-eval",
        "chart-evidence-v2",
    )

    assert captured["factory"] == ("codex", "gpt-eval")
    assert execution["provider"] == "codex"
