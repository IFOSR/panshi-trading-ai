from dataclasses import dataclass


@dataclass(frozen=True)
class MacdResult:
    dif: list[float]
    dea: list[float]
    histogram: list[float]
    fast: int
    slow: int
    signal: int
    formula_version: str = "macd-ema-seed-first-v1"


def _ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (span + 1.0)
    result = [values[0]]
    for value in values[1:]:
        result.append(alpha * value + (1.0 - alpha) * result[-1])
    return result


def macd(
    values: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> MacdResult:
    if not values:
        raise ValueError("values cannot be empty")
    if not 0 < fast < slow or signal <= 0:
        raise ValueError("MACD periods are invalid")

    fast_ema = _ema(values, fast)
    slow_ema = _ema(values, slow)
    dif = [fast_value - slow_value for fast_value, slow_value in zip(fast_ema, slow_ema)]
    dea = _ema(dif, signal)
    histogram = [2.0 * (dif_value - dea_value) for dif_value, dea_value in zip(dif, dea)]
    return MacdResult(
        dif=dif,
        dea=dea,
        histogram=histogram,
        fast=fast,
        slow=slow,
        signal=signal,
    )
