from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from trading_agent.strategy.context import StrategyContext
from trading_agent.workflows.analysis import AnalysisWorkflow


@dataclass(frozen=True)
class BacktestCosts:
    fees: float
    slippage: float
    rollover_cost: float
    unavailable_fills: int
    same_day_close_cost: float = 0.0


@dataclass(frozen=True)
class BacktestResult:
    chronology_valid: bool
    walk_forward_valid: bool
    look_ahead_violations: int
    gross_pnl: float
    net_pnl: float
    fees: float
    slippage: float
    same_day_close_cost: float
    rollover_cost: float
    fill_count: int
    unavailable_fills: int
    price_limit_blocks: int
    rollovers: int
    production_strategy_cases: int
    production_strategy_execution_coverage: float
    strategy_selection_accuracy: float
    strategy_type_coverage: float
    signal_transition_accuracy: float
    trigger_invalidation_coverage: float
    strategy_action_contradictions: int


@dataclass(frozen=True)
class _Bar:
    timestamp: datetime
    trading_date: date
    contract: str
    open: float
    close: float
    limit_up: float
    limit_down: float
    available: bool


@dataclass(frozen=True)
class _Order:
    decision_time: datetime
    fill_time: datetime
    feature_timestamps: tuple[datetime, ...]
    target_position: int
    fold: str


@dataclass(frozen=True)
class _Fold:
    name: str
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime


@dataclass(frozen=True)
class _CostModel:
    fee_per_contract: float
    slippage_per_contract: float
    same_day_close_fee_per_contract: float
    rollover_cost_per_contract: float
    multiplier: float


@dataclass(frozen=True)
class _StrategyCase:
    decision_time: datetime
    fill_time: datetime
    fold: str
    context: StrategyContext
    expected_strategy: str | None
    allowed_actions: tuple[str, ...]
    signal_stage: str
    upgrade_conditions: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]


def net_pnl(gross_pnl: float, costs: BacktestCosts) -> float:
    return (
        gross_pnl
        - costs.fees
        - costs.slippage
        - costs.rollover_cost
        - costs.same_day_close_cost
    )


def _timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    try:
        return datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from error


def _date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO-8601 date") from error


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    return value


def _sequence(value: object, field: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be an array")
    return value


def _parse_bars(values: object) -> list[_Bar]:
    bars = []
    for index, value in enumerate(_sequence(values, "bars")):
        item = _mapping(value, f"bars[{index}]")
        bars.append(
            _Bar(
                timestamp=_timestamp(item.get("timestamp"), f"bars[{index}].timestamp"),
                trading_date=_date(
                    item.get("trading_date"), f"bars[{index}].trading_date"
                ),
                contract=str(item["contract"]),
                open=float(item["open"]),
                close=float(item["close"]),
                limit_up=float(item["limit_up"]),
                limit_down=float(item["limit_down"]),
                available=bool(item.get("available", True)),
            )
        )
    if not bars:
        raise ValueError("bars must not be empty")
    if any(left.timestamp >= right.timestamp for left, right in zip(bars, bars[1:])):
        raise ValueError("bars must be strictly chronological")
    return bars


def _parse_folds(values: object) -> list[_Fold]:
    folds = []
    for index, value in enumerate(_sequence(values, "walk_forward")):
        item = _mapping(value, f"walk_forward[{index}]")
        fold = _Fold(
            name=str(item["name"]),
            train_start=_timestamp(
                item.get("train_start"), f"walk_forward[{index}].train_start"
            ),
            train_end=_timestamp(
                item.get("train_end"), f"walk_forward[{index}].train_end"
            ),
            test_start=_timestamp(
                item.get("test_start"), f"walk_forward[{index}].test_start"
            ),
            test_end=_timestamp(item.get("test_end"), f"walk_forward[{index}].test_end"),
        )
        if not (
            fold.train_start <= fold.train_end < fold.test_start <= fold.test_end
        ):
            raise ValueError("walk-forward folds must train before their held-out test window")
        folds.append(fold)
    if not folds:
        raise ValueError("walk_forward must contain at least one fold")
    if len({fold.name for fold in folds}) != len(folds):
        raise ValueError("walk-forward fold names must be unique")
    if any(left.test_end >= right.test_start for left, right in zip(folds, folds[1:])):
        raise ValueError("walk-forward test windows must be chronological and non-overlapping")
    return folds


def _parse_costs(value: object) -> _CostModel:
    item = _mapping(value, "costs")
    costs = _CostModel(
        fee_per_contract=float(item.get("fee_per_contract", 0.0)),
        slippage_per_contract=float(item.get("slippage_per_contract", 0.0)),
        same_day_close_fee_per_contract=float(
            item.get("same_day_close_fee_per_contract", 0.0)
        ),
        rollover_cost_per_contract=float(item.get("rollover_cost_per_contract", 0.0)),
        multiplier=float(item.get("multiplier", 1.0)),
    )
    if min(asdict(costs).values()) < 0:
        raise ValueError("backtest costs and multiplier must be non-negative")
    if costs.multiplier == 0:
        raise ValueError("backtest multiplier must be positive")
    return costs


def _parse_strategy_cases(values: object) -> list[_StrategyCase]:
    cases = []
    for index, value in enumerate(_sequence(values, "strategy_cases")):
        item = _mapping(value, f"strategy_cases[{index}]")
        expected = _mapping(item.get("expected"), f"strategy_cases[{index}].expected")
        allowed_actions = tuple(
            str(action)
            for action in _sequence(
                expected.get("allowed_actions"),
                f"strategy_cases[{index}].expected.allowed_actions",
            )
        )
        if not allowed_actions:
            raise ValueError("strategy case allowed_actions must not be empty")
        cases.append(
            _StrategyCase(
                decision_time=_timestamp(
                    item.get("decision_time"),
                    f"strategy_cases[{index}].decision_time",
                ),
                fill_time=_timestamp(
                    item.get("fill_time"),
                    f"strategy_cases[{index}].fill_time",
                ),
                fold=str(item["fold"]),
                context=StrategyContext.model_validate(
                    _mapping(item.get("context"), f"strategy_cases[{index}].context")
                ),
                expected_strategy=(
                    str(expected["strategy"])
                    if expected.get("strategy") is not None
                    else None
                ),
                allowed_actions=allowed_actions,
                signal_stage=str(expected["signal_stage"]),
                upgrade_conditions=tuple(
                    str(condition)
                    for condition in _sequence(
                        expected.get("upgrade_conditions"),
                        (
                            f"strategy_cases[{index}].expected."
                            "upgrade_conditions"
                        ),
                    )
                ),
                invalidation_conditions=tuple(
                    str(condition)
                    for condition in _sequence(
                        expected.get("invalidation_conditions"),
                        (
                            f"strategy_cases[{index}].expected."
                            "invalidation_conditions"
                        ),
                    )
                ),
            )
        )
    if not cases:
        raise ValueError("strategy_cases must not be empty")
    if any(
        left.decision_time > right.decision_time for left, right in zip(cases, cases[1:])
    ):
        raise ValueError("strategy cases must be chronological")
    if any(left.fill_time > right.fill_time for left, right in zip(cases, cases[1:])):
        raise ValueError("strategy case fills must be chronological")
    return cases


def _validate_strategy_cases(
    cases: Sequence[_StrategyCase],
    folds: Sequence[_Fold],
    bars_by_time: Mapping[datetime, _Bar],
) -> None:
    folds_by_name = {fold.name: fold for fold in folds}
    for case in cases:
        fold = folds_by_name.get(case.fold)
        if fold is None:
            raise ValueError(f"unknown walk-forward fold: {case.fold}")
        if not fold.test_start <= case.decision_time <= fold.test_end:
            raise ValueError("strategy case must remain inside its held-out test window")
        if not fold.test_start <= case.fill_time <= fold.test_end:
            raise ValueError("strategy case must remain inside its held-out test window")
        if case.fill_time < case.decision_time:
            raise ValueError("strategy case fill cannot precede its decision")
        if case.fill_time not in bars_by_time:
            raise ValueError("strategy case fill_time must match a structured historical bar")
        cutoff = _timestamp(case.context.data_cutoff_time, "strategy context data_cutoff_time")
        if cutoff > case.decision_time:
            raise ValueError("look-ahead strategy context exceeds decision_time")


APPROVED_STRATEGIES = {
    "TREND_BREAKOUT_LONG",
    "TREND_PULLBACK_LONG",
    "TREND_BREAKOUT_SHORT",
    "TREND_PULLBACK_SHORT",
    "RANGE_REVERSAL_LONG",
    "RANGE_REVERSAL_SHORT",
}


def _target_position(action: str, strategy: str | None, current: int) -> int | None:
    if action in {"WAIT_FOR_DATA", "WAIT_FOR_SETUP", "WATCH_ENTRY", "HOLD"}:
        return None
    if action == "EXIT":
        return 0
    if action == "REDUCE":
        return current - 1 if current > 0 else current + 1 if current < 0 else None
    if action == "ENTER_CONDITIONAL":
        if strategy and strategy.endswith("_LONG"):
            return 1
        if strategy and strategy.endswith("_SHORT"):
            return -1
    if action == "ADD_CONDITIONAL":
        return current + 1 if current > 0 else current - 1 if current < 0 else None
    return None


def _position_matches_context(position: int, context: StrategyContext) -> bool:
    return (
        (position == 0 and context.position.value == "FLAT")
        or (position > 0 and context.position.value == "LONG")
        or (position < 0 and context.position.value == "SHORT")
    )


def _evaluate_production_strategy(
    cases: Sequence[_StrategyCase],
    bars_by_time: Mapping[datetime, _Bar],
) -> tuple[int, float, float, float, float, float, int, list[_Order]]:
    executed = 0
    strategy_matches = 0
    contradictions = 0
    signal_matches = 0
    required_conditions = 0
    covered_conditions = 0
    selected_strategies: set[str] = set()
    orders: list[_Order] = []
    current_position = 0
    workflow = AnalysisWorkflow(max_provider_attempts=1)
    for index, case in enumerate(cases):
        if not _position_matches_context(current_position, case.context):
            raise ValueError(
                "strategy case context position does not match simulated position"
            )
        cutoff = _timestamp(
            case.context.data_cutoff_time,
            "strategy context data_cutoff_time",
        )
        data_age_seconds = (case.decision_time - cutoff).total_seconds()
        context = case.context.model_copy(
            update={"data_age_seconds": max(0.0, data_age_seconds)}
        )
        result = workflow.run(
            f"strategy-eval-{index}",
            f"strategy-eval-{index}",
            context,
            lambda: {"provider": "structured-strategy-eval"},
        )
        executed += 1
        if result.decision.strategy in APPROVED_STRATEGIES:
            selected_strategies.add(result.decision.strategy)
        if result.decision.strategy == case.expected_strategy:
            strategy_matches += 1
        if result.decision.action.value not in case.allowed_actions:
            contradictions += 1
        signal_matches += result.decision.signal_stage == case.signal_stage
        for expected, actual in (
            (case.upgrade_conditions, result.decision.upgrade_conditions),
            (
                case.invalidation_conditions,
                result.decision.invalidation_conditions,
            ),
        ):
            required = set(expected)
            required_conditions += len(required)
            covered_conditions += len(required & set(actual))
        target = _target_position(
            result.decision.action.value,
            result.decision.strategy,
            current_position,
        )
        if target is not None and target != current_position:
            bar = bars_by_time[case.fill_time]
            delta = target - current_position
            orders.append(
                _Order(
                    decision_time=case.decision_time,
                    fill_time=case.fill_time,
                    feature_timestamps=(cutoff,),
                    target_position=target,
                    fold=case.fold,
                )
            )
            limit_blocked = (delta > 0 and bar.open >= bar.limit_up) or (
                delta < 0 and bar.open <= bar.limit_down
            )
            if bar.available and not limit_blocked:
                current_position = target
    total = len(cases)
    return (
        total,
        executed / total,
        strategy_matches / total,
        len(selected_strategies) / len(APPROVED_STRATEGIES),
        signal_matches / total,
        (
            covered_conditions / required_conditions
            if required_conditions
            else 1.0
        ),
        contradictions,
        orders,
    )


def run_backtest(dataset: Mapping[str, object]) -> BacktestResult:
    bars = _parse_bars(dataset.get("bars"))
    folds = _parse_folds(dataset.get("walk_forward"))
    strategy_cases = _parse_strategy_cases(dataset.get("strategy_cases"))
    costs = _parse_costs(dataset.get("costs", {}))
    bars_by_time = {bar.timestamp: bar for bar in bars}
    _validate_strategy_cases(strategy_cases, folds, bars_by_time)
    (
        production_strategy_cases,
        production_strategy_execution_coverage,
        strategy_selection_accuracy,
        strategy_type_coverage,
        signal_transition_accuracy,
        trigger_invalidation_coverage,
        strategy_action_contradictions,
        orders,
    ) = _evaluate_production_strategy(strategy_cases, bars_by_time)

    orders_by_fill: dict[datetime, list[_Order]] = defaultdict(list)
    for order in orders:
        orders_by_fill[order.fill_time].append(order)

    position = 0
    position_opened_trading_date: date | None = None
    gross_cash = 0.0
    net_cash = 0.0
    fees = 0.0
    slippage = 0.0
    same_day_close_cost = 0.0
    rollover_cost = 0.0
    fill_count = 0
    unavailable_fills = 0
    price_limit_blocks = 0
    rollovers = 0
    previous_bar: _Bar | None = None

    for bar in bars:
        if previous_bar is not None and bar.contract != previous_bar.contract and position:
            gap_adjustment = position * (bar.open - previous_bar.close) * costs.multiplier
            gross_cash -= gap_adjustment
            net_cash -= gap_adjustment
            charge = abs(position) * costs.rollover_cost_per_contract
            rollover_cost += charge
            net_cash -= charge
            rollovers += 1

        for order in orders_by_fill[bar.timestamp]:
            delta = order.target_position - position
            if delta == 0:
                continue
            if not bar.available:
                unavailable_fills += 1
                continue
            limit_blocked = (delta > 0 and bar.open >= bar.limit_up) or (
                delta < 0 and bar.open <= bar.limit_down
            )
            if limit_blocked:
                price_limit_blocks += 1
                unavailable_fills += 1
                continue

            closing_quantity = (
                min(abs(position), abs(delta)) if position * delta < 0 else 0
            )
            raw_price = bar.open
            execution_price = raw_price + (
                costs.slippage_per_contract if delta > 0 else -costs.slippage_per_contract
            )
            gross_cash -= delta * raw_price * costs.multiplier
            net_cash -= delta * execution_price * costs.multiplier

            fee = abs(delta) * costs.fee_per_contract
            slip = abs(delta) * costs.slippage_per_contract * costs.multiplier
            fees += fee
            slippage += slip
            net_cash -= fee
            if (
                closing_quantity
                and position_opened_trading_date is not None
                and position_opened_trading_date == bar.trading_date
            ):
                close_charge = (
                    closing_quantity * costs.same_day_close_fee_per_contract
                )
                same_day_close_cost += close_charge
                net_cash -= close_charge

            old_position = position
            position = order.target_position
            if position == 0:
                position_opened_trading_date = None
            elif old_position == 0 or old_position * position < 0:
                position_opened_trading_date = bar.trading_date
            fill_count += 1
        previous_bar = bar

    final_bar = bars[-1]
    gross_pnl_value = gross_cash + position * final_bar.close * costs.multiplier
    net_pnl_value = net_cash + position * final_bar.close * costs.multiplier
    return BacktestResult(
        chronology_valid=True,
        walk_forward_valid=True,
        look_ahead_violations=0,
        gross_pnl=gross_pnl_value,
        net_pnl=net_pnl_value,
        fees=fees,
        slippage=slippage,
        same_day_close_cost=same_day_close_cost,
        rollover_cost=rollover_cost,
        fill_count=fill_count,
        unavailable_fills=unavailable_fills,
        price_limit_blocks=price_limit_blocks,
        rollovers=rollovers,
        production_strategy_cases=production_strategy_cases,
        production_strategy_execution_coverage=production_strategy_execution_coverage,
        strategy_selection_accuracy=strategy_selection_accuracy,
        strategy_type_coverage=strategy_type_coverage,
        signal_transition_accuracy=signal_transition_accuracy,
        trigger_invalidation_coverage=trigger_invalidation_coverage,
        strategy_action_contradictions=strategy_action_contradictions,
    )


def evaluate_strategy_dataset(path: Path) -> BacktestResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return run_backtest(_mapping(payload, "strategy dataset"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(asdict(evaluate_strategy_dataset(args.dataset)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
