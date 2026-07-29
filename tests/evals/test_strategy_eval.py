from __future__ import annotations

from copy import deepcopy

import pytest

from evals.run_strategy_eval import _target_position, run_backtest


def strategy_dataset() -> dict[str, object]:
    return {
        "bars": [
            {
                "timestamp": "2026-01-05T09:00:00",
                "trading_date": "2026-01-05",
                "contract": "AU2606",
                "open": 100.0,
                "close": 101.0,
                "limit_up": 110.0,
                "limit_down": 90.0,
                "available": True,
            },
            {
                "timestamp": "2026-01-05T10:00:00",
                "trading_date": "2026-01-05",
                "contract": "AU2606",
                "open": 102.0,
                "close": 102.0,
                "limit_up": 112.0,
                "limit_down": 92.0,
                "available": True,
            },
            {
                "timestamp": "2026-01-05T11:00:00",
                "trading_date": "2026-01-05",
                "contract": "AU2612",
                "open": 104.0,
                "close": 104.0,
                "limit_up": 114.0,
                "limit_down": 94.0,
                "available": True,
            },
            {
                "timestamp": "2026-01-05T12:00:00",
                "trading_date": "2026-01-05",
                "contract": "AU2612",
                "open": 105.0,
                "close": 105.0,
                "limit_up": 115.0,
                "limit_down": 95.0,
                "available": True,
            },
            {
                "timestamp": "2026-01-05T13:00:00",
                "trading_date": "2026-01-05",
                "contract": "AU2612",
                "open": 90.0,
                "close": 90.0,
                "limit_up": 100.0,
                "limit_down": 90.0,
                "available": True,
            },
            {
                "timestamp": "2026-01-05T14:00:00",
                "trading_date": "2026-01-05",
                "contract": "AU2612",
                "open": 95.0,
                "close": 95.0,
                "limit_up": 105.0,
                "limit_down": 85.0,
                "available": False,
            },
        ],
        "walk_forward": [
            {
                "name": "fold-1",
                "train_start": "2025-01-01T00:00:00",
                "train_end": "2025-12-31T23:59:59",
                "test_start": "2026-01-05T08:00:00",
                "test_end": "2026-01-05T15:00:00",
            }
        ],
        "strategy_cases": [
            {
                "decision_time": "2026-01-05T08:59:00",
                "fill_time": "2026-01-05T09:00:00",
                "fold": "fold-1",
                "context": {
                    "contract": "AU2606",
                    "timeframe": "1d",
                    "state_bar_closed": True,
                    "data_cutoff_time": "2026-01-05T08:58:00",
                    "data_age_seconds": 60,
                    "trend_score": 3,
                    "price_location": "ABOVE_BOLL_UPPER",
                    "open_interest_change": 100,
                    "momentum_state": "BULLISH_STRENGTHENING",
                    "price_confirmation": True,
                    "price_confirmation_direction": "BULLISH",
                    "price_confirmation_type": "BREAKOUT",
                    "position": "FLAT",
                    "account_risk_limit": 0.01,
                    "proposed_risk": 0.005
                },
                "expected": {
                    "strategy": "TREND_BREAKOUT_LONG",
                    "allowed_actions": ["ENTER_CONDITIONAL"],
                    "signal_stage": "BULLISH_BREAKOUT",
                    "upgrade_conditions": ["数据有效、价格确认且风险通过"],
                    "invalidation_conditions": ["结构失效或风险引擎否决"],
                }
            }
        ],
        "costs": {
            "fee_per_contract": 1.0,
            "slippage_per_contract": 0.5,
            "same_day_close_fee_per_contract": 2.0,
            "rollover_cost_per_contract": 1.0,
            "multiplier": 1.0,
        },
    }


def test_backtest_rejects_look_ahead_features() -> None:
    dataset = strategy_dataset()
    cases = dataset["strategy_cases"]
    assert isinstance(cases, list)
    context = cases[0]["context"]
    assert isinstance(context, dict)
    context["data_cutoff_time"] = "2026-01-05T09:00:01"

    with pytest.raises(ValueError, match="look-ahead"):
        run_backtest(dataset)


def test_backtest_rejects_non_chronological_bars() -> None:
    dataset = strategy_dataset()
    bars = dataset["bars"]
    assert isinstance(bars, list)
    bars[0], bars[1] = bars[1], bars[0]

    with pytest.raises(ValueError, match="chronological"):
        run_backtest(dataset)


def test_backtest_rejects_non_chronological_order_fills() -> None:
    dataset = strategy_dataset()
    cases = dataset["strategy_cases"]
    assert isinstance(cases, list)
    second = deepcopy(cases[0])
    cases.append(second)
    cases[0]["decision_time"] = "2026-01-05T08:20:00"
    cases[0]["fill_time"] = "2026-01-05T10:00:00"
    cases[0]["context"]["data_cutoff_time"] = "2026-01-05T08:19:00"
    cases[1]["decision_time"] = "2026-01-05T08:30:00"
    cases[1]["fill_time"] = "2026-01-05T09:00:00"
    cases[1]["context"]["data_cutoff_time"] = "2026-01-05T08:29:00"

    with pytest.raises(ValueError, match="chronological"):
        run_backtest(dataset)


def test_backtest_rejects_orders_outside_walk_forward_test_window() -> None:
    dataset = strategy_dataset()
    cases = dataset["strategy_cases"]
    assert isinstance(cases, list)
    cases[0]["decision_time"] = "2025-12-31T12:00:00"
    cases[0]["fill_time"] = "2026-01-05T09:00:00"
    cases[0]["context"]["data_cutoff_time"] = "2025-12-31T11:59:00"

    with pytest.raises(ValueError, match="held-out test window"):
        run_backtest(dataset)


def test_backtest_rejects_context_position_that_does_not_match_simulator() -> None:
    dataset = strategy_dataset()
    cases = dataset["strategy_cases"]
    assert isinstance(cases, list)
    context = cases[0]["context"]
    expected = cases[0]["expected"]
    assert isinstance(context, dict)
    assert isinstance(expected, dict)
    context["position"] = "LONG"
    context["forced_exit"] = True
    expected["allowed_actions"] = ["EXIT"]

    with pytest.raises(ValueError, match="simulated position"):
        run_backtest(dataset)


def test_backtest_models_costs_rollovers_and_unavailable_fills() -> None:
    result = run_backtest(deepcopy(strategy_dataset()))

    assert result.chronology_valid is True
    assert result.walk_forward_valid is True
    assert result.look_ahead_violations == 0
    assert result.gross_pnl == pytest.approx(-7.0)
    assert result.fees == pytest.approx(1.0)
    assert result.slippage == pytest.approx(0.5)
    assert result.same_day_close_cost == 0
    assert result.rollover_cost == pytest.approx(1.0)
    assert result.net_pnl == pytest.approx(-9.5)
    assert result.fill_count == 1
    assert result.unavailable_fills == 0
    assert result.price_limit_blocks == 0
    assert result.rollovers == 1
    assert result.production_strategy_cases == 1
    assert result.production_strategy_execution_coverage == 1.0
    assert result.strategy_selection_accuracy == 1.0
    assert result.strategy_action_contradictions == 0
    assert result.signal_transition_accuracy == 1.0
    assert result.trigger_invalidation_coverage == 1.0


def test_strategy_eval_counts_production_action_contradictions() -> None:
    dataset = strategy_dataset()
    cases = dataset["strategy_cases"]
    assert isinstance(cases, list)
    expected = cases[0]["expected"]
    assert isinstance(expected, dict)
    expected["allowed_actions"] = ["WAIT_FOR_SETUP"]

    result = run_backtest(dataset)

    assert result.production_strategy_cases == 1
    assert result.strategy_action_contradictions == 1


def test_strategy_eval_recomputes_data_age_from_decision_time() -> None:
    dataset = strategy_dataset()
    cases = dataset["strategy_cases"]
    assert isinstance(cases, list)
    context = cases[0]["context"]
    assert isinstance(context, dict)
    context["data_cutoff_time"] = "2026-01-01T08:58:00"
    context["data_age_seconds"] = 0

    result = run_backtest(dataset)

    assert result.strategy_action_contradictions == 1


def test_strategy_eval_reports_fraction_of_all_six_strategies_covered() -> None:
    result = run_backtest(strategy_dataset())

    assert result.strategy_type_coverage == pytest.approx(1 / 6)


def test_reduce_decreases_position_by_one_while_exit_flattens() -> None:
    assert _target_position("REDUCE", "TREND_BREAKOUT_LONG", 3) == 2
    assert _target_position("REDUCE", "TREND_BREAKOUT_SHORT", -3) == -2
    assert _target_position("EXIT", "TREND_BREAKOUT_LONG", 3) == 0
    assert _target_position("EXIT", "TREND_BREAKOUT_SHORT", -3) == 0


def test_same_trading_date_fee_spans_night_and_day_calendar_dates() -> None:
    dataset = strategy_dataset()
    dataset["bars"] = [
        {
            "timestamp": "2026-01-02T21:00:00+08:00",
            "trading_date": "2026-01-05",
            "contract": "AU2606",
            "open": 100.0,
            "close": 101.0,
            "limit_up": 110.0,
            "limit_down": 90.0,
        },
        {
            "timestamp": "2026-01-05T09:00:00+08:00",
            "trading_date": "2026-01-05",
            "contract": "AU2606",
            "open": 102.0,
            "close": 102.0,
            "limit_up": 112.0,
            "limit_down": 92.0,
        },
    ]
    dataset["walk_forward"] = [
        {
            "name": "fold-1",
            "train_start": "2025-01-01T00:00:00+08:00",
            "train_end": "2025-12-31T23:59:59+08:00",
            "test_start": "2026-01-02T20:00:00+08:00",
            "test_end": "2026-01-05T10:00:00+08:00",
        }
    ]
    cases = dataset["strategy_cases"]
    assert isinstance(cases, list)
    entry = cases[0]
    entry["decision_time"] = "2026-01-02T20:59:00+08:00"
    entry["fill_time"] = "2026-01-02T21:00:00+08:00"
    entry["context"]["data_cutoff_time"] = "2026-01-02T20:58:00+08:00"
    exit_case = deepcopy(entry)
    exit_case["decision_time"] = "2026-01-05T08:59:00+08:00"
    exit_case["fill_time"] = "2026-01-05T09:00:00+08:00"
    exit_case["context"]["data_cutoff_time"] = "2026-01-05T08:58:00+08:00"
    exit_case["context"]["position"] = "LONG"
    exit_case["context"]["forced_exit"] = True
    exit_case["expected"] = {
        "strategy": "TREND_BREAKOUT_LONG",
        "allowed_actions": ["EXIT"],
        "signal_stage": "BULLISH_BREAKOUT",
        "upgrade_conditions": ["数据有效、价格确认且风险通过"],
        "invalidation_conditions": ["结构失效或风险引擎否决"],
    }
    dataset["strategy_cases"] = [entry, exit_case]

    result = run_backtest(dataset)

    assert result.same_day_close_cost == pytest.approx(2.0)
