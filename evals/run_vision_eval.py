"""Vision benchmark runner consumes labeled JSONL without image preprocessing."""

from evals.release_gate import evaluate_release


def run(metrics: dict[str, float]) -> bool:
    return evaluate_release(metrics).passed
