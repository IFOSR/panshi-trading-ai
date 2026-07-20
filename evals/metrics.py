from collections.abc import Sequence


def accepted_precision(correct: int, accepted: int) -> float:
    return correct / accepted if accepted else 0.0


def coverage(accepted: int, total: int) -> float:
    return accepted / total if total else 0.0


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * quantile))
    return ordered[index]
