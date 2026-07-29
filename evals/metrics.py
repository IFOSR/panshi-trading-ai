from collections import defaultdict
from collections.abc import Hashable, Sequence


def accepted_precision(correct: int, accepted: int) -> float:
    return correct / accepted if accepted else 0.0


def coverage(accepted: float, total: float) -> float:
    return accepted / total if total else 0.0


def percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * quantile))
    return ordered[index]


def accuracy(labels: Sequence[Hashable], predictions: Sequence[Hashable]) -> float:
    if not labels:
        return 0.0
    return sum(label == prediction for label, prediction in zip(labels, predictions)) / len(
        labels
    )


def macro_f1(labels: Sequence[Hashable], predictions: Sequence[Hashable]) -> float:
    classes = set(labels) | set(predictions)
    if not classes:
        return 0.0
    scores = []
    for class_name in classes:
        true_positive = sum(
            label == class_name and prediction == class_name
            for label, prediction in zip(labels, predictions)
        )
        false_positive = sum(
            label != class_name and prediction == class_name
            for label, prediction in zip(labels, predictions)
        )
        false_negative = sum(
            label == class_name and prediction != class_name
            for label, prediction in zip(labels, predictions)
        )
        denominator = 2 * true_positive + false_positive + false_negative
        scores.append(2 * true_positive / denominator if denominator else 0.0)
    return sum(scores) / len(scores)


def expected_calibration_error(
    confidences: Sequence[float],
    correctness: Sequence[bool],
    *,
    bins: int = 10,
) -> float:
    if not confidences:
        return 0.0
    grouped: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for confidence, correct in zip(confidences, correctness):
        bounded = min(1.0, max(0.0, confidence))
        grouped[min(bins - 1, int(bounded * bins))].append((bounded, correct))
    error = 0.0
    for values in grouped.values():
        bin_confidence = sum(confidence for confidence, _ in values) / len(values)
        bin_accuracy = sum(correct for _, correct in values) / len(values)
        error += len(values) / len(confidences) * abs(bin_accuracy - bin_confidence)
    return error
