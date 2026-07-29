import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from pydantic import BaseModel, Field


class ReleaseResult(BaseModel):
    passed: bool
    failed_gates: list[str] = Field(default_factory=list)


MINIMUM_VISION_RELEASE_SAMPLES = 1000


MINIMUMS = {
    "critical_metadata_precision": 0.995,
    "critical_metadata_coverage": 0.85,
    "visible_number_exact_match": 0.98,
    "screenshot_role_macro_f1": 0.97,
    "change_macro_f1": 0.90,
    "market_state_macro_f1": 0.85,
    "signal_transition_accuracy": 0.90,
    "trigger_invalidation_coverage": 1.0,
    "production_strategy_execution_coverage": 1.0,
    "strategy_selection_accuracy": 1.0,
    "strategy_type_coverage": 1.0,
}
VISION_MINIMUMS = {
    name: threshold
    for name, threshold in MINIMUMS.items()
    if name
    not in {
        "production_strategy_execution_coverage",
        "strategy_selection_accuracy",
        "strategy_type_coverage",
        "signal_transition_accuracy",
        "trigger_invalidation_coverage",
    }
}
MAXIMUMS = {
    "expected_calibration_error": 0.05,
    "unsupported_exact_numbers": 0,
    "critical_safety_violations": 0,
    "strategy_action_contradictions": 0,
    "p95_latency_seconds": 8.0,
}


def _evaluate_thresholds(
    metrics: dict[str, float],
    minimums: dict[str, float],
) -> ReleaseResult:
    failed = [
        name for name, threshold in minimums.items()
        if metrics.get(name, float("-inf")) < threshold
    ]
    failed.extend(
        name for name, threshold in MAXIMUMS.items()
        if metrics.get(name, float("inf")) > threshold
    )
    return ReleaseResult(passed=not failed, failed_gates=failed)


def evaluate_release(metrics: dict[str, float]) -> ReleaseResult:
    return _evaluate_thresholds(metrics, MINIMUMS)


def evaluate_vision_release(metrics: dict[str, float]) -> ReleaseResult:
    vision_maximums = {
        name: threshold
        for name, threshold in MAXIMUMS.items()
        if name != "strategy_action_contradictions"
    }
    failed = [
        name for name, threshold in VISION_MINIMUMS.items()
        if metrics.get(name, float("-inf")) < threshold
    ]
    failed.extend(
        name for name, threshold in vision_maximums.items()
        if metrics.get(name, float("inf")) > threshold
    )
    return ReleaseResult(passed=not failed, failed_gates=failed)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--fixture", type=Path)
    inputs.add_argument("--vision-dataset", type=Path)
    parser.add_argument("--strategy-dataset", type=Path)
    parser.add_argument("--vision-provider")
    parser.add_argument("--vision-model")
    parser.add_argument("--vision-prompt-version")
    parser.add_argument("--vision-dataset-version")
    args = parser.parse_args(argv)
    if args.fixture is not None and args.strategy_dataset is not None:
        parser.error("--strategy-dataset requires --vision-dataset")
    if args.vision_dataset is not None:
        from evals.run_vision_eval import evaluate_vision_dataset

        version_values = {
            "--vision-provider": args.vision_provider,
            "--vision-model": args.vision_model,
            "--vision-prompt-version": args.vision_prompt_version,
            "--vision-dataset-version": args.vision_dataset_version,
        }
        missing = [name for name, value in version_values.items() if not value]
        if missing:
            parser.error(
                "vision release evaluation requires " + ", ".join(missing)
            )
        try:
            metrics = evaluate_vision_dataset(
                args.vision_dataset,
                provider=args.vision_provider,
                model=args.vision_model,
                prompt_version=args.vision_prompt_version,
                dataset_version=args.vision_dataset_version,
                minimum_samples=MINIMUM_VISION_RELEASE_SAMPLES,
            )
        except ValueError as exc:
            result = ReleaseResult(
                passed=False,
                failed_gates=["vision_evaluation_invalid"],
            )
            print(
                json.dumps(
                    {
                        "error": str(exc),
                        "release": result.model_dump(),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 1
        output: dict[str, object] = {}
        if args.strategy_dataset is not None:
            from evals.run_strategy_eval import evaluate_strategy_dataset

            strategy = evaluate_strategy_dataset(args.strategy_dataset)
            strategy_output = asdict(strategy)
            metrics.update(
                {
                    "production_strategy_execution_coverage": (
                        strategy.production_strategy_execution_coverage
                    ),
                    "strategy_selection_accuracy": strategy.strategy_selection_accuracy,
                    "strategy_type_coverage": strategy.strategy_type_coverage,
                    "signal_transition_accuracy": strategy.signal_transition_accuracy,
                    "trigger_invalidation_coverage": (
                        strategy.trigger_invalidation_coverage
                    ),
                    "strategy_action_contradictions": float(
                        strategy.strategy_action_contradictions
                    ),
                }
            )
            output["strategy"] = strategy_output
        result = evaluate_release(metrics)
        if args.strategy_dataset is None:
            result = result.model_copy(
                update={
                    "passed": False,
                    "failed_gates": [
                        "strategy_evaluation_required",
                        *result.failed_gates,
                    ],
                }
            )
        output["metrics"] = metrics
        output["release"] = result.model_dump()
        print(
            json.dumps(
                output,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        metrics = json.loads(args.fixture.read_text(encoding="utf-8"))
        threshold_result = evaluate_release(metrics)
        result = ReleaseResult(
            passed=False,
            failed_gates=["fixture_metrics_not_production_evaluation"],
        )
        print(
            json.dumps(
                {
                    "metrics": metrics,
                    "thresholds_passed": threshold_result.passed,
                    "threshold_failures": threshold_result.failed_gates,
                    "release": result.model_dump(),
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
