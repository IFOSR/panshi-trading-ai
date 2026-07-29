import json
from copy import deepcopy
from pathlib import Path

from pytest import CaptureFixture

from evals.release_gate import MINIMUM_VISION_RELEASE_SAMPLES
from evals.release_gate import evaluate_release
from evals.release_gate import evaluate_vision_release
from evals.release_gate import main as release_main
from trading_agent.vision.prompts import prompt_sha256


def passing_metrics() -> dict[str, float]:
    return {
        "critical_metadata_precision": 0.996,
        "critical_metadata_coverage": 0.86,
        "visible_number_exact_match": 0.99,
        "screenshot_role_macro_f1": 0.98,
        "change_macro_f1": 0.91,
        "market_state_macro_f1": 0.86,
        "signal_transition_accuracy": 0.91,
        "expected_calibration_error": 0.04,
        "unsupported_exact_numbers": 0,
        "critical_safety_violations": 0,
        "strategy_action_contradictions": 0,
        "production_strategy_execution_coverage": 1.0,
        "strategy_selection_accuracy": 1.0,
        "strategy_type_coverage": 1.0,
        "trigger_invalidation_coverage": 1.0,
        "p95_latency_seconds": 7.5,
    }


def vision_record(
    *,
    action: str = "HOLD",
    image_path: str = "chart.png",
    dataset_version: str = "vision-benchmark-v1",
) -> dict[str, object]:
    return {
        "record_id": "vision-1",
        "dataset_version": dataset_version,
        "image_path": image_path,
        "split": "test",
        "labels": {
            "critical_metadata": {"instrument": "AU"},
            "visible_numbers": {"last_price": "105"},
            "screenshot_role": "STATE_DAILY",
            "change": "NEW",
            "market_state": "T+",
            "signal_transition": "HOLD",
            "triggers": [],
            "invalidations": [],
            "allowed_actions": ["HOLD"],
        },
    }


def vision_execution(*, action: str = "HOLD") -> dict[str, object]:
    return {
        "prediction": {
            "accepted": True,
            "critical_metadata": {"instrument": "AU"},
            "visible_numbers": {"last_price": "105"},
            "screenshot_role": "STATE_DAILY",
            "change": "UNCHANGED",
            "market_state": "T+",
            "signal_transition": "HOLD",
            "triggers": [],
            "invalidations": [],
            "action": action,
            "confidence": 1.0,
            "critical_safety_violations": [],
        },
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "prompt_version": "chart-evidence-v2",
        "prompt_sha256": prompt_sha256("chart-evidence-v2"),
        "latency_seconds": 1.0,
        "cost": 0.01,
    }


def six_strategy_dataset() -> dict[str, object]:
    definitions = [
        (3, "ABOVE_BOLL_UPPER", "BULLISH", "BREAKOUT", "TREND_BREAKOUT_LONG"),
        (3, "BETWEEN_UPPER_AND_MID", "BULLISH", "PULLBACK", "TREND_PULLBACK_LONG"),
        (-3, "BELOW_BOLL_LOWER", "BEARISH", "BREAKOUT", "TREND_BREAKOUT_SHORT"),
        (
            -3,
            "BELOW_BOLL_MID_ABOVE_LOWER",
            "BEARISH",
            "PULLBACK",
            "TREND_PULLBACK_SHORT",
        ),
        (0, "AT_RANGE_SUPPORT", "BULLISH", "PULLBACK", "RANGE_REVERSAL_LONG"),
        (0, "AT_RANGE_RESISTANCE", "BEARISH", "PULLBACK", "RANGE_REVERSAL_SHORT"),
    ]
    bars = []
    cases = []
    for index, (
        trend_score,
        price_location,
        direction,
        confirmation_type,
        strategy,
    ) in enumerate(definitions, start=9):
        fill_time = f"2026-01-05T{index:02d}:00:00"
        decision_time = f"2026-01-05T{index - 1:02d}:59:00"
        cutoff_time = f"2026-01-05T{index - 1:02d}:58:00"
        bars.append(
            {
                "timestamp": fill_time,
                "trading_date": "2026-01-05",
                "contract": "AU2606",
                "open": float(100 + index),
                "close": float(101 + index),
                "limit_up": float(120 + index),
                "limit_down": float(80 + index),
                "available": True,
            }
        )
        cases.append(
            {
                "decision_time": decision_time,
                "fill_time": fill_time,
                "fold": "fold-1",
                "context": {
                    "contract": "AU2606",
                    "timeframe": "1d",
                    "state_bar_closed": True,
                    "data_cutoff_time": cutoff_time,
                    "data_age_seconds": 0,
                    "trend_score": trend_score,
                    "price_location": price_location,
                    "open_interest_change": 100,
                    "momentum_state": "BULLISH_STRENGTHENING",
                    "price_confirmation": True,
                    "price_confirmation_direction": direction,
                    "price_confirmation_type": confirmation_type,
                    "position": "FLAT",
                },
                "expected": {
                    "strategy": strategy,
                    "allowed_actions": ["WAIT_FOR_SETUP"],
                    "signal_stage": f"{direction}_{confirmation_type}",
                    "upgrade_conditions": ["数据有效、价格确认且风险通过"],
                    "invalidation_conditions": ["结构失效或风险引擎否决"],
                },
            }
        )
    return {
        "bars": bars,
        "walk_forward": [
            {
                "name": "fold-1",
                "train_start": "2025-01-01T00:00:00",
                "train_end": "2025-12-31T23:59:59",
                "test_start": "2026-01-05T08:00:00",
                "test_end": "2026-01-05T15:00:00",
            }
        ],
        "strategy_cases": cases,
        "costs": {},
    }


def write_datasets(
    tmp_path: Path,
    *,
    vision: dict[str, object],
    strategy: dict[str, object],
) -> tuple[Path, Path]:
    vision_path = tmp_path / "vision.jsonl"
    strategy_path = tmp_path / "strategy.json"
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(b"original-image")
    vision["image_path"] = str(image_path)
    write_vision_dataset(vision_path, vision)
    strategy_path.write_text(json.dumps(strategy), encoding="utf-8")
    return vision_path, strategy_path


def write_vision_dataset(
    path: Path,
    record: dict[str, object],
    *,
    count: int = MINIMUM_VISION_RELEASE_SAMPLES,
) -> None:
    rows = []
    original_path = Path(str(record["image_path"]))
    original_bytes = original_path.read_bytes()
    for index in range(count):
        current = deepcopy(record)
        current["record_id"] = f"vision-{index}"
        image_path = original_path.with_name(
            f"{original_path.stem}-{index}{original_path.suffix}"
        )
        image_path.write_bytes(original_bytes + index.to_bytes(8, "big"))
        current["image_path"] = str(image_path)
        rows.append(json.dumps(current))
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def vision_cli_args(vision_path: Path) -> list[str]:
    return [
        "--vision-dataset",
        str(vision_path),
        "--vision-provider",
        "codex",
        "--vision-model",
        "gpt-5.6-sol",
        "--vision-prompt-version",
        "chart-evidence-v2",
        "--vision-dataset-version",
        "vision-benchmark-v1",
    ]


def test_release_fails_on_any_critical_safety_violation() -> None:
    metrics = passing_metrics()
    metrics["critical_safety_violations"] = 1

    result = evaluate_release(metrics)

    assert result.passed is False
    assert "critical_safety_violations" in result.failed_gates


def test_passing_fixture_satisfies_every_hard_gate() -> None:
    result = evaluate_release(passing_metrics())

    assert result.passed is True
    assert result.failed_gates == []


def test_vision_release_requires_only_fields_owned_by_visual_evidence() -> None:
    metrics = passing_metrics()
    for downstream_field in (
        "signal_transition_accuracy",
        "trigger_invalidation_coverage",
        "strategy_action_contradictions",
        "production_strategy_execution_coverage",
        "strategy_selection_accuracy",
        "strategy_type_coverage",
    ):
        metrics.pop(downstream_field)

    result = evaluate_vision_release(metrics)

    assert result.passed is True


def test_fixture_cli_cannot_replace_executed_vision_release(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    fixture_path = tmp_path / "passing.json"
    fixture_path.write_text(json.dumps(passing_metrics()), encoding="utf-8")

    exit_code = release_main(["--fixture", str(fixture_path)])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert output["thresholds_passed"] is True
    assert "fixture_metrics_not_production_evaluation" in output["release"]["failed_gates"]


def test_release_requires_strategy_evaluation(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch,
) -> None:
    vision_path = tmp_path / "vision.jsonl"
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(b"original-image")
    write_vision_dataset(
        vision_path,
        vision_record(image_path=str(image_path)),
    )
    monkeypatch.setattr(
        "evals.run_vision_eval.execute_vision_provider",
        lambda *_: vision_execution(),
    )

    exit_code = release_main(vision_cli_args(vision_path))

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert "strategy_evaluation_required" in output["release"]["failed_gates"]


def test_release_cli_executes_all_six_production_strategies(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch,
) -> None:
    vision_path, strategy_path = write_datasets(
        tmp_path,
        vision=vision_record(),
        strategy=six_strategy_dataset(),
    )

    calls: list[Path] = []

    def execute(path: Path, *_: str) -> dict[str, object]:
        calls.append(path)
        return vision_execution()

    monkeypatch.setattr("evals.run_vision_eval.execute_vision_provider", execute)

    exit_code = release_main(
        [
            *vision_cli_args(vision_path),
            "--strategy-dataset",
            str(strategy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert len(calls) == MINIMUM_VISION_RELEASE_SAMPLES
    assert len(set(calls)) == MINIMUM_VISION_RELEASE_SAMPLES
    assert output["release"]["passed"] is True
    assert output["strategy"]["production_strategy_execution_coverage"] == 1.0
    assert output["strategy"]["strategy_type_coverage"] == 1.0


def test_strategy_contradiction_fails_release_even_when_vision_gates_pass(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch,
) -> None:
    strategy = deepcopy(six_strategy_dataset())
    cases = strategy["strategy_cases"]
    assert isinstance(cases, list)
    cases[0]["expected"]["allowed_actions"] = ["ENTER_CONDITIONAL"]
    vision_path, strategy_path = write_datasets(
        tmp_path,
        vision=vision_record(),
        strategy=strategy,
    )

    monkeypatch.setattr(
        "evals.run_vision_eval.execute_vision_provider",
        lambda *_: vision_execution(),
    )

    exit_code = release_main(
        [
            *vision_cli_args(vision_path),
            "--strategy-dataset",
            str(strategy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert "strategy_action_contradictions" in output["release"]["failed_gates"]


def test_vision_provider_cannot_inject_a_strategy_action_contradiction(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch,
) -> None:
    vision_path, strategy_path = write_datasets(
        tmp_path,
        vision=vision_record(action="ENTER_CONDITIONAL"),
        strategy=six_strategy_dataset(),
    )

    monkeypatch.setattr(
        "evals.run_vision_eval.execute_vision_provider",
        lambda *_: vision_execution(action="ENTER_CONDITIONAL"),
    )

    exit_code = release_main(
        [
            *vision_cli_args(vision_path),
            "--strategy-dataset",
            str(strategy_path),
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["metrics"]["strategy_action_contradictions"] == 0


def test_release_rejects_prefilled_prediction_without_provider_execution(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(b"original-image")
    record = vision_record(image_path=str(image_path))
    record["prediction"] = vision_execution()["prediction"]
    vision_path = tmp_path / "vision.jsonl"
    vision_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    exit_code = release_main(vision_cli_args(vision_path))

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert "prediction" in output["error"]
    assert "vision_evaluation_invalid" in output["release"]["failed_gates"]


def test_release_rejects_vision_dataset_below_minimum_sample_size(
    tmp_path: Path,
    monkeypatch,
    capsys: CaptureFixture[str],
) -> None:
    image_path = tmp_path / "chart.png"
    image_path.write_bytes(b"original-image")
    vision_path = tmp_path / "vision.jsonl"
    write_vision_dataset(
        vision_path,
        vision_record(image_path=str(image_path)),
        count=1,
    )
    monkeypatch.setattr(
        "evals.run_vision_eval.execute_vision_provider",
        lambda *_: vision_execution(),
    )

    exit_code = release_main(vision_cli_args(vision_path))

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert "minimum" in output["error"]
    assert "vision_evaluation_invalid" in output["release"]["failed_gates"]
