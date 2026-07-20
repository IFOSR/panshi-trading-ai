import argparse
import json
from pathlib import Path

from pydantic import BaseModel, Field


class ReleaseResult(BaseModel):
    passed: bool
    failed_gates: list[str] = Field(default_factory=list)


MINIMUMS = {
    "critical_metadata_precision": 0.995,
    "critical_metadata_coverage": 0.85,
    "visible_number_exact_match": 0.98,
    "screenshot_role_macro_f1": 0.97,
    "change_macro_f1": 0.90,
    "market_state_macro_f1": 0.85,
    "signal_transition_accuracy": 0.90,
    "trigger_invalidation_coverage": 1.0,
}
MAXIMUMS = {
    "expected_calibration_error": 0.05,
    "unsupported_exact_numbers": 0,
    "critical_safety_violations": 0,
    "strategy_action_contradictions": 0,
    "p95_latency_seconds": 8.0,
}


def evaluate_release(metrics: dict[str, float]) -> ReleaseResult:
    failed = [
        name for name, threshold in MINIMUMS.items()
        if metrics.get(name, float("-inf")) < threshold
    ]
    failed.extend(
        name for name, threshold in MAXIMUMS.items()
        if metrics.get(name, float("inf")) > threshold
    )
    return ReleaseResult(passed=not failed, failed_gates=failed)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_release(json.loads(args.fixture.read_text(encoding="utf-8")))
    print(result.model_dump_json(indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
