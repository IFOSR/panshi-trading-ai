from trading_agent.quant.swings import confirmed_swing_highs


def test_swing_high_requires_right_side_confirmation() -> None:
    assert confirmed_swing_highs([1, 2, 3, 2], left=2, right=2) == []
    assert confirmed_swing_highs([1, 2, 3, 2, 1], left=2, right=2) == [2]
