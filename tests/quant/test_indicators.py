import pytest

from trading_agent.quant.boll import boll
from trading_agent.quant.atr import atr
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


def test_macd_regression_and_formula_version() -> None:
    result = macd([float(value) for value in range(1, 31)])

    assert result.dif[-1] == pytest.approx(5.701696584370296)
    assert result.dea[-1] == pytest.approx(5.172206699422461)
    assert result.histogram[-1] == pytest.approx(1.0589797698956698)
    assert result.formula_version == "macd-ema-seed-first-v1"


def test_atr_uses_wilder_smoothing_and_is_versioned() -> None:
    result = atr(
        highs=[12.0, 13.0, 15.0, 14.0],
        lows=[10.0, 11.0, 12.0, 11.0],
        closes=[11.0, 12.0, 13.0, 12.0],
        period=3,
    )

    assert result.values[-1] == pytest.approx(23.0 / 9.0)
    assert result.formula_version == "atr-wilder-v1"
