from evals.release_gate import evaluate_release


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
        "trigger_invalidation_coverage": 1.0,
        "p95_latency_seconds": 7.5,
    }


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
