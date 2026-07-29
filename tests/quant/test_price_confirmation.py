from trading_agent.quant.confirmation import classify_price_confirmation


def test_new_close_beyond_prior_range_is_a_breakout() -> None:
    opens = [100.0] * 22
    highs = [110.0] * 21 + [112.0]
    lows = [90.0] * 22
    closes = [105.0] * 21 + [111.0]

    result = classify_price_confirmation(
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        boll_mid=104.0,
    )

    assert result.confirmed is True
    assert result.direction == "BULLISH"
    assert result.kind == "BREAKOUT"
    assert result.reference_price == 110.0


def test_second_close_beyond_prior_range_is_a_hold() -> None:
    opens = [100.0] * 22
    highs = [110.0] * 20 + [112.0, 113.0]
    lows = [90.0] * 22
    closes = [105.0] * 20 + [111.0, 112.0]

    result = classify_price_confirmation(
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        boll_mid=104.0,
    )

    assert result.confirmed is True
    assert result.direction == "BULLISH"
    assert result.kind == "HOLD"
    assert result.reference_price == 110.0


def test_bearish_rejection_of_boll_mid_is_a_pullback_confirmation() -> None:
    opens = [100.0] * 21 + [104.0]
    highs = [110.0] * 21 + [106.0]
    lows = [90.0] * 21 + [98.0]
    closes = [100.0] * 21 + [99.0]

    result = classify_price_confirmation(
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        boll_mid=102.0,
    )

    assert result.confirmed is True
    assert result.direction == "BEARISH"
    assert result.kind == "PULLBACK"
    assert result.reference_price == 102.0


def test_unclosed_bar_has_unknown_confirmation_state() -> None:
    result = classify_price_confirmation(
        opens=[100.0] * 22,
        highs=[110.0] * 22,
        lows=[90.0] * 22,
        closes=[100.0] * 22,
        boll_mid=100.0,
        last_bar_closed=False,
    )

    assert result.confirmed is None
    assert result.direction == "UNKNOWN"
    assert result.kind == "UNKNOWN"


def test_twenty_one_bars_have_unknown_confirmation_state() -> None:
    result = classify_price_confirmation(
        opens=[100.0] * 21,
        highs=[110.0] * 21,
        lows=[90.0] * 21,
        closes=[100.0] * 21,
        boll_mid=100.0,
    )

    assert result.confirmed is None
    assert result.direction == "UNKNOWN"
    assert result.kind == "UNKNOWN"


def test_closed_ambiguous_structure_is_known_not_confirmed() -> None:
    result = classify_price_confirmation(
        opens=[100.0] * 22,
        highs=[110.0] * 22,
        lows=[90.0] * 22,
        closes=[100.0] * 22,
        boll_mid=100.0,
    )

    assert result.confirmed is False
    assert result.direction == "UNKNOWN"
    assert result.kind == "UNKNOWN"
