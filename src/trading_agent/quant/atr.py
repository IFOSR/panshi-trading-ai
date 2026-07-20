from dataclasses import dataclass


@dataclass(frozen=True)
class AtrResult:
    values: list[float]
    period: int
    formula_version: str = "atr-wilder-v1"


def atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> AtrResult:
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("ATR inputs must have equal lengths")
    if period <= 0 or len(closes) < period:
        raise ValueError("invalid ATR period")
    true_ranges: list[float] = []
    for index, (high, low) in enumerate(zip(highs, lows)):
        if low > high:
            raise ValueError("low cannot exceed high")
        previous_close = closes[index - 1] if index else closes[index]
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    initial = sum(true_ranges[:period]) / period
    values = [initial]
    for current in true_ranges[period:]:
        values.append((values[-1] * (period - 1) + current) / period)
    return AtrResult(values=values, period=period)
