"""Vision benchmark runner consumes labeled JSONL without image preprocessing."""

import argparse
import json
from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any

from evals.metrics import (
    accepted_precision,
    accuracy,
    coverage,
    expected_calibration_error,
    macro_f1,
    percentile,
)
from evals.release_gate import evaluate_vision_release


VisionExecutor = Callable[[Path, str, str, str], Mapping[str, object]]
MINIMUM_VISION_EVAL_SAMPLES = 1000


def run(
    dataset: Path,
    *,
    provider: str,
    model: str,
    prompt_version: str,
    dataset_version: str,
    minimum_samples: int = MINIMUM_VISION_EVAL_SAMPLES,
    executor: VisionExecutor | None = None,
) -> bool:
    metrics = evaluate_vision_dataset(
        dataset,
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        dataset_version=dataset_version,
        minimum_samples=minimum_samples,
        executor=executor,
    )
    return evaluate_vision_release(metrics).passed


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _values(value: object) -> set[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return set(value)
    return set()


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    return float(value)


def evaluate_vision_records(records: Sequence[Mapping[str, object]]) -> dict[str, float]:
    critical_correct = 0
    critical_accepted = 0
    critical_total = 0
    visible_correct = 0
    visible_total = 0
    required_conditions = 0
    covered_conditions = 0
    unsupported_numbers = 0
    safety_violations = 0
    contradictions = 0
    accepted_analyses = 0
    roles: list[object] = []
    predicted_roles: list[object] = []
    changes: list[object] = []
    predicted_changes: list[object] = []
    market_states: list[object] = []
    predicted_market_states: list[object] = []
    transitions: list[object] = []
    predicted_transitions: list[object] = []
    confidences: list[float] = []
    confidence_correctness: list[bool] = []
    latencies: list[float] = []
    costs: list[float] = []

    for record in records:
        labels = _mapping(record.get("labels"))
        prediction = _mapping(record.get("prediction"))
        label_metadata = _mapping(labels.get("critical_metadata"))
        predicted_metadata = _mapping(prediction.get("critical_metadata"))
        critical_total += len(label_metadata)
        for name, expected in label_metadata.items():
            actual = predicted_metadata.get(name)
            if actual is not None:
                critical_accepted += 1
                critical_correct += actual == expected

        label_numbers = _mapping(labels.get("visible_numbers"))
        predicted_numbers = _mapping(prediction.get("visible_numbers"))
        visible_total += len(label_numbers)
        visible_correct += sum(
            predicted_numbers.get(name) == expected for name, expected in label_numbers.items()
        )
        unsupported_numbers += sum(
            name not in label_numbers and value is not None
            for name, value in predicted_numbers.items()
        )

        for label_name, expected_values in (
            ("triggers", labels.get("triggers")),
            ("invalidations", labels.get("invalidations")),
        ):
            if label_name not in prediction:
                continue
            required = _values(expected_values)
            predicted = _values(prediction.get(label_name))
            required_conditions += len(required)
            covered_conditions += len(required & predicted)

        role = labels.get("screenshot_role")
        predicted_role = prediction.get("screenshot_role")
        roles.append(role)
        predicted_roles.append(predicted_role)
        changes.append(labels.get("change"))
        predicted_changes.append(prediction.get("change"))
        market_states.append(labels.get("market_state"))
        predicted_market_states.append(prediction.get("market_state"))
        if "signal_transition" in prediction:
            transitions.append(labels.get("signal_transition"))
            predicted_transitions.append(prediction.get("signal_transition"))

        confidence = _number(prediction.get("confidence", 0.0), "prediction.confidence")
        confidences.append(confidence)
        confidence_correctness.append(role == predicted_role)
        accepted_analyses += bool(prediction.get("accepted", True))
        latency = _number(record.get("latency_seconds", 0.0), "latency_seconds")
        cost = _number(record.get("cost", 0.0), "cost")
        latencies.append(latency)
        costs.append(cost)

        violations = prediction.get("critical_safety_violations", [])
        safety_violations += violations if isinstance(violations, int) else len(_values(violations))
        allowed_actions = _values(labels.get("allowed_actions"))
        action = prediction.get("action")
        if "action" in prediction and allowed_actions and action not in allowed_actions:
            contradictions += 1

    total_cost = sum(costs)
    metrics = {
        "critical_metadata_precision": accepted_precision(
            critical_correct, critical_accepted
        ),
        "critical_metadata_coverage": coverage(critical_accepted, critical_total),
        "visible_number_exact_match": coverage(visible_correct, visible_total),
        "screenshot_role_macro_f1": macro_f1(roles, predicted_roles),
        "change_macro_f1": macro_f1(changes, predicted_changes),
        "market_state_macro_f1": macro_f1(market_states, predicted_market_states),
        "expected_calibration_error": expected_calibration_error(
            confidences, confidence_correctness
        ),
        "unsupported_exact_numbers": float(unsupported_numbers),
        "critical_safety_violations": float(safety_violations),
        "strategy_action_contradictions": float(contradictions),
        "p50_latency_seconds": percentile(latencies, 0.5),
        "p95_latency_seconds": percentile(latencies, 0.95),
        "total_cost": total_cost,
        "mean_cost_per_analysis": coverage(total_cost, len(records)),
        "cost_per_accepted_analysis": coverage(total_cost, accepted_analyses),
    }
    if transitions:
        metrics["signal_transition_accuracy"] = accuracy(
            transitions,
            predicted_transitions,
        )
    if required_conditions:
        metrics["trigger_invalidation_coverage"] = coverage(
            covered_conditions,
            required_conditions,
        )
    return metrics


def load_vision_records(path: Path) -> list[Mapping[str, object]]:
    if path.suffix == ".jsonl":
        values = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
        values = payload.get("records", []) if isinstance(payload, Mapping) else payload
    if not isinstance(values, list) or not all(isinstance(value, Mapping) for value in values):
        raise ValueError("vision dataset must contain a list of prediction/label records")
    if not values:
        raise ValueError("vision dataset must not be empty")
    return values


def _flatten_visible_numbers(value: object, prefix: str = "") -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    flattened: dict[str, object] = {}
    for name, item in value.items():
        key = f"{prefix}.{name}" if prefix else str(name)
        if isinstance(item, Mapping):
            flattened.update(_flatten_visible_numbers(item, key))
        elif isinstance(item, (int, float, str)) and not isinstance(item, bool):
            flattened[key] = item
    return flattened


def execute_vision_provider(
    image_path: Path,
    provider: str,
    model: str,
    prompt_version: str,
) -> Mapping[str, object]:
    from trading_agent.providers.base import VisionRequest
    from trading_agent.providers.factory import configured_vision_provider
    from trading_agent.vision.privacy import PrivacyAssessment
    from trading_agent.vision.prompts import provider_prompt_sha256

    selected = configured_vision_provider(provider, model=model)

    started_at = perf_counter()
    evidence = selected.analyze(
        VisionRequest(
            prompt_version=prompt_version,
            image_paths=[image_path],
            storage_root=image_path.parent,
            privacy_assessment=PrivacyAssessment(safe_for_model=True),
        )
    )
    latency_seconds = perf_counter() - started_at
    facts = evidence.strategy_facts
    market_state = {
        "BULLISH": "T+",
        "BEARISH": "T-",
        "RANGE": "R",
        "UNKNOWN": "U",
    }[facts.trend_bias]
    confidences = [item.confidence for item in evidence.observations]
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return {
        "prediction": {
            "accepted": evidence.allowed_usage.value != "BLOCKED",
            "critical_metadata": {
                "instrument": evidence.instrument,
                "contract": evidence.contract,
                "timeframe": evidence.timeframe,
                "cutoff_time": evidence.cutoff_time,
                "last_bar_closed": evidence.last_bar_closed,
            },
            "visible_numbers": _flatten_visible_numbers(evidence.indicators),
            "screenshot_role": evidence.image_role,
            "market_state": market_state,
            "confidence": confidence,
            "critical_safety_violations": [],
        },
        "provider": evidence.provider,
        "model": evidence.model,
        "prompt_version": evidence.prompt_version,
        "prompt_sha256": (
            evidence.prompt_sha256
            or provider_prompt_sha256(
                evidence.prompt_version,
                provider=evidence.provider,
                image_suffixes=[image_path.suffix],
            )
        ),
        "latency_seconds": latency_seconds,
        "cost": 0.0,
    }


def _validated_image_path(dataset_path: Path, raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("vision record image_path is required")
    image_path = Path(raw_path)
    if not image_path.is_absolute():
        image_path = dataset_path.parent / image_path
    image_path = image_path.resolve()
    if not image_path.is_file():
        raise ValueError(f"vision record original image does not exist: {image_path}")
    return image_path


def _change_fingerprint(prediction: Mapping[str, object]) -> str:
    evidence_fields = {
        key: prediction.get(key)
        for key in (
            "critical_metadata",
            "visible_numbers",
            "screenshot_role",
            "market_state",
        )
    }
    return json.dumps(
        evidence_fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _validate_execution(
    execution: Mapping[str, object],
    *,
    provider: str,
    model: str,
    prompt_version: str,
    image_suffixes: list[str],
) -> None:
    from trading_agent.vision.prompts import provider_prompt_sha256

    expected = {
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "prompt_sha256": provider_prompt_sha256(
            prompt_version,
            provider=provider,
            image_suffixes=image_suffixes,
        ),
    }
    for field, value in expected.items():
        if execution.get(field) != value:
            raise ValueError(
                f"vision execution {field} mismatch: "
                f"expected {value!r}, got {execution.get(field)!r}"
            )
    if not isinstance(execution.get("prediction"), Mapping):
        raise ValueError("vision provider execution must return prediction")


def evaluate_vision_dataset(
    path: Path,
    *,
    provider: str,
    model: str,
    prompt_version: str,
    dataset_version: str,
    minimum_samples: int = MINIMUM_VISION_EVAL_SAMPLES,
    executor: VisionExecutor | None = None,
) -> dict[str, float]:
    from trading_agent.vision.prompts import resolve_prompt

    resolve_prompt(prompt_version)
    records = load_vision_records(path)
    if any("prediction" in record for record in records):
        raise ValueError(
            "vision dataset must not contain prefilled prediction; "
            "the configured provider must execute"
        )
    if minimum_samples < 1:
        raise ValueError("minimum vision sample size must be positive")
    if len(records) < minimum_samples:
        raise ValueError(
            f"vision dataset has {len(records)} records; "
            f"minimum required is {minimum_samples}"
        )

    record_ids: set[str] = set()
    image_hashes: set[str] = set()
    runtime_records: list[Mapping[str, object]] = []
    execute = executor or execute_vision_provider
    for record in records:
        if record.get("split") != "test":
            raise ValueError("vision release evaluation requires the test split")
        if record.get("dataset_version") != dataset_version:
            raise ValueError(
                "vision dataset version mismatch: "
                f"expected {dataset_version!r}, got {record.get('dataset_version')!r}"
            )
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("vision record_id is required")
        if record_id in record_ids:
            raise ValueError(f"duplicate vision record_id: {record_id}")
        record_ids.add(record_id)
        labels = record.get("labels")
        if not isinstance(labels, Mapping):
            raise ValueError(f"vision record {record_id} labels are required")
        image_path = _validated_image_path(path, record.get("image_path"))
        image_hash = sha256(image_path.read_bytes()).hexdigest()
        if image_hash in image_hashes:
            raise ValueError(
                f"duplicate original image in vision dataset: {image_hash}"
            )
        image_hashes.add(image_hash)
        previous_execution: Mapping[str, object] | None = None
        if record.get("previous_image_path") is not None:
            previous_image_path = _validated_image_path(
                path,
                record.get("previous_image_path"),
            )
            previous_execution = execute(
                previous_image_path,
                provider,
                model,
                prompt_version,
            )
            _validate_execution(
                previous_execution,
                provider=provider,
                model=model,
                prompt_version=prompt_version,
                image_suffixes=[previous_image_path.suffix],
            )
        execution = execute(image_path, provider, model, prompt_version)
        _validate_execution(
            execution,
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            image_suffixes=[image_path.suffix],
        )
        prediction = dict(_mapping(execution["prediction"]))
        prediction["change"] = (
            "NEW"
            if previous_execution is None
            else (
                "UNCHANGED"
                if _change_fingerprint(
                    _mapping(previous_execution["prediction"])
                )
                == _change_fingerprint(prediction)
                else "CHANGED"
            )
        )
        runtime_records.append(
            {
                "labels": labels,
                "prediction": prediction,
                "latency_seconds": execution.get("latency_seconds", 0.0),
                "cost": execution.get("cost", 0.0),
            }
        )
    return evaluate_vision_records(runtime_records)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument("--dataset-version", required=True)
    args = parser.parse_args(argv)
    metrics = evaluate_vision_dataset(
        args.dataset,
        provider=args.provider,
        model=args.model,
        prompt_version=args.prompt_version,
        dataset_version=args.dataset_version,
    )
    result = evaluate_vision_release(metrics)
    print(
        json.dumps(
            {"metrics": metrics, "release": result.model_dump()},
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
