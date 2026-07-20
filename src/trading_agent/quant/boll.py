from dataclasses import dataclass
from statistics import fmean, pstdev


@dataclass(frozen=True)
class BollResult:
    mid: float
    upper: float
    lower: float
    period: int
    deviations: float


def boll(
    values: list[float],
    period: int = 20,
    deviations: float = 2.0,
) -> BollResult:
    if period <= 1:
        raise ValueError("period must be greater than one")
    if len(values) < period:
        raise ValueError("not enough values for the requested period")

    window = values[-period:]
    mid = fmean(window)
    standard_deviation = pstdev(window)
    return BollResult(
        mid=mid,
        upper=mid + deviations * standard_deviation,
        lower=mid - deviations * standard_deviation,
        period=period,
        deviations=deviations,
    )

