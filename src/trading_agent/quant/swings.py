def confirmed_swing_highs(
    values: list[float],
    left: int = 2,
    right: int = 2,
) -> list[int]:
    if left < 1 or right < 1:
        raise ValueError("left and right confirmation windows must be positive")

    confirmed: list[int] = []
    for index in range(left, len(values) - right):
        current = values[index]
        left_values = values[index - left : index]
        right_values = values[index + 1 : index + right + 1]
        if all(current > value for value in left_values + right_values):
            confirmed.append(index)
    return confirmed


def confirmed_swing_lows(
    values: list[float],
    left: int = 2,
    right: int = 2,
) -> list[int]:
    return confirmed_swing_highs([-value for value in values], left=left, right=right)
