from dataclasses import dataclass


MIN_PRICE_CONFIRMATION_BARS = 22


@dataclass(frozen=True)
class PriceConfirmation:
    confirmed: bool | None
    direction: str = "UNKNOWN"
    kind: str = "UNKNOWN"
    reference_price: float | None = None


def classify_price_confirmation(
    *,
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    boll_mid: float,
    last_bar_closed: bool = True,
) -> PriceConfirmation:
    if not last_bar_closed:
        return PriceConfirmation(None)
    if min(map(len, (opens, highs, lows, closes))) < MIN_PRICE_CONFIRMATION_BARS:
        return PriceConfirmation(None)
    reference_high = max(highs[-22:-2])
    reference_low = min(lows[-22:-2])
    previous_close = closes[-2]
    latest_close = closes[-1]

    if latest_close > reference_high:
        return PriceConfirmation(
            True,
            "BULLISH",
            "HOLD" if previous_close > reference_high else "BREAKOUT",
            reference_high,
        )
    if latest_close < reference_low:
        return PriceConfirmation(
            True,
            "BEARISH",
            "HOLD" if previous_close < reference_low else "BREAKOUT",
            reference_low,
        )
    if lows[-1] <= boll_mid <= latest_close and latest_close > opens[-1]:
        return PriceConfirmation(True, "BULLISH", "PULLBACK", boll_mid)
    if highs[-1] >= boll_mid >= latest_close and latest_close < opens[-1]:
        return PriceConfirmation(True, "BEARISH", "PULLBACK", boll_mid)
    return PriceConfirmation(False)
