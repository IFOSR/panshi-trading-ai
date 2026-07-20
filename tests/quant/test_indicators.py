import pytest

from trading_agent.quant.boll import boll
from trading_agent.quant.macd import macd


def test_boll_uses_population_standard_deviation() -> None:
    result = boll([float(value) for value in range(1, 21)], period=20, deviations=2)

    assert result.mid == pytest.approx(10.5)
    assert result.upper == pytest.approx(22.0325625947)
    assert result.lower == pytest.approx(-1.0325625947)


def test_macd_is_zero_for_constant_prices() -> None:
    result = macd([100.0] * 40, fast=12, slow=26, signal=9)

    assert result.dif[-1] == pytest.approx(0)
    assert result.dea[-1] == pytest.approx(0)
    assert result.histogram[-1] == pytest.approx(0)

