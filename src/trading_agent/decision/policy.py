from pydantic import BaseModel

from trading_agent.domain.decision import ActionDecision
from trading_agent.domain.enums import (
    ActionType, MarketState, MilestoneStatus, PositionDirection,
)
from trading_agent.domain.milestone import StrategyEvaluation
from trading_agent.risk.models import RiskResult
from trading_agent.strategy.context import StrategyContext
from trading_agent.strategies.contracts import StrategySignal


class DecisionInput(BaseModel):
    evaluation: StrategyEvaluation
    context: StrategyContext
    risk: RiskResult
    forced_exit: bool = False
    position_invalidated: bool = False
    reduce_required: bool = False
    add_confirmation: bool = False


class StrategyDecisionInput(BaseModel):
    signal: StrategySignal
    context: StrategyContext
    risk: RiskResult
    action_step_number: int
    forced_exit: bool = False
    position_invalidated: bool = False
    reduce_required: bool = False
    add_confirmation: bool = False


MILESTONE_LABELS = {
    1: "数据有效性",
    2: "市场状态",
    3: "策略许可",
    4: "价格位置",
    5: "量仓行为",
    6: "动量",
    7: "价格确认",
    8: "风险与动作",
}


def _market_state(result: str) -> MarketState:
    if result == "T+":
        return MarketState.T_PLUS
    if result == "T-":
        return MarketState.T_MINUS
    if result == "R":
        return MarketState.RANGE
    return MarketState.U


def next_milestone_for(blocking: list[int]) -> str:
    if blocking:
        number = min(blocking)
        return f"补齐第{number}步：{MILESTONE_LABELS[number]}"
    return "等待下一次策略状态更新"


def decide_action(item: DecisionInput) -> ActionDecision:
    by_number = {step.number: step for step in item.evaluation.steps}
    supporting = [
        number for number, step in by_number.items()
        if step.status == MilestoneStatus.CONFIRMED
    ]
    blocking = [
        number for number, step in by_number.items()
        if step.status in {MilestoneStatus.BLOCKED, MilestoneStatus.INVALIDATED}
    ]
    if item.risk.status == "APPROVED":
        supporting = sorted(set(supporting) | {8})
        blocking = [number for number in blocking if number != 8]
    else:
        supporting = [number for number in supporting if number != 8]
        blocking = sorted(set(blocking) | {8})
    reason_codes = list(dict.fromkeys(
        item.risk.reason_codes
        + [blocker for step in by_number.values() for blocker in step.blockers]
    ))
    market_state = _market_state(by_number[2].result)
    strategy = None if by_number[3].result == "NONE" else by_number[3].result
    position = item.context.position
    strategy_steps_ready = not any(
        by_number[number].status
        in {MilestoneStatus.BLOCKED, MilestoneStatus.INVALIDATED}
        for number in range(1, 8)
    )

    if item.forced_exit and position in {PositionDirection.LONG, PositionDirection.SHORT}:
        action = ActionType.EXIT
    elif item.risk.status == "VETO":
        action = ActionType.WAIT_FOR_SETUP
    elif by_number[1].status == MilestoneStatus.BLOCKED:
        action = ActionType.WAIT_FOR_DATA
    elif item.position_invalidated and position in {
        PositionDirection.LONG, PositionDirection.SHORT,
    }:
        action = ActionType.EXIT
    elif item.reduce_required and position in {
        PositionDirection.LONG, PositionDirection.SHORT,
    }:
        action = ActionType.REDUCE
    elif item.add_confirmation and position in {
        PositionDirection.LONG, PositionDirection.SHORT,
    } and (
        item.risk.status == "APPROVED"
        and strategy_steps_ready
        and by_number[7].status == MilestoneStatus.CONFIRMED
    ):
        action = ActionType.ADD_CONDITIONAL
    elif (
        position == PositionDirection.FLAT
        and strategy
        and strategy_steps_ready
        and by_number[7].status == MilestoneStatus.CONFIRMED
        and item.risk.status == "APPROVED"
    ):
        action = ActionType.ENTER_CONDITIONAL
    elif position in {PositionDirection.LONG, PositionDirection.SHORT}:
        action = ActionType.HOLD
    else:
        action = ActionType.WAIT_FOR_SETUP

    if action == ActionType.ENTER_CONDITIONAL:
        supporting = sorted(set(supporting) | {1, 2, 3, 7, 8})
    if action == ActionType.WAIT_FOR_DATA and not blocking:
        blocking = [1]
    return ActionDecision(
        action=action,
        market_state=market_state,
        position_scope=position,
        strategy=strategy,
        signal_stage=by_number[7].result,
        supporting_steps=supporting,
        blocking_steps=blocking,
        reason_codes=reason_codes,
        evidence_refs=list(dict.fromkeys(
            ref for step in by_number.values() for ref in step.evidence_refs
        )),
        next_milestone=next_milestone_for(blocking),
        upgrade_conditions=["数据有效、价格确认且风险通过"],
        invalidation_conditions=["结构失效或风险引擎否决"],
        missing_information=reason_codes if action == ActionType.WAIT_FOR_DATA else [],
    )


def decide_action_from_strategy(item: StrategyDecisionInput) -> ActionDecision:
    signal = item.signal
    supporting = list(signal.supporting_steps)
    blocking = list(signal.blocking_steps)
    if item.risk.status == "APPROVED":
        supporting = sorted(set(supporting) | {item.action_step_number})
    else:
        blocking = sorted(set(blocking) | {item.action_step_number})
    reason_codes = list(dict.fromkeys(
        item.risk.reason_codes + signal.reason_codes
    ))
    market_state = _market_state(signal.market_state)
    position = item.context.position
    strategy_ready = not signal.blocking_steps

    if item.forced_exit and position in {
        PositionDirection.LONG,
        PositionDirection.SHORT,
    }:
        action = ActionType.EXIT
    elif item.risk.status == "VETO":
        action = ActionType.WAIT_FOR_SETUP
    elif not signal.data_valid:
        action = ActionType.WAIT_FOR_DATA
    elif item.position_invalidated and position in {
        PositionDirection.LONG,
        PositionDirection.SHORT,
    }:
        action = ActionType.EXIT
    elif item.reduce_required and position in {
        PositionDirection.LONG,
        PositionDirection.SHORT,
    }:
        action = ActionType.REDUCE
    elif (
        item.add_confirmation
        and position in {PositionDirection.LONG, PositionDirection.SHORT}
        and item.risk.status == "APPROVED"
        and strategy_ready
        and signal.price_confirmed
    ):
        action = ActionType.ADD_CONDITIONAL
    elif (
        position == PositionDirection.FLAT
        and signal.setup_code
        and strategy_ready
        and signal.price_confirmed
        and item.risk.status == "APPROVED"
    ):
        action = ActionType.ENTER_CONDITIONAL
    elif position in {PositionDirection.LONG, PositionDirection.SHORT}:
        action = ActionType.HOLD
    else:
        action = ActionType.WAIT_FOR_SETUP

    if action == ActionType.WAIT_FOR_DATA and not blocking:
        blocking = [signal.blocking_steps[0] if signal.blocking_steps else 1]
    next_milestone = (
        signal.next_milestone
        if action in {ActionType.WAIT_FOR_DATA, ActionType.WAIT_FOR_SETUP}
        else "等待下一次策略状态更新"
    )
    return ActionDecision(
        action=action,
        market_state=market_state,
        position_scope=position,
        strategy=signal.setup_code,
        signal_stage=signal.signal_stage,
        supporting_steps=supporting,
        blocking_steps=blocking,
        reason_codes=reason_codes,
        evidence_refs=signal.evidence_refs,
        next_milestone=next_milestone,
        upgrade_conditions=signal.upgrade_conditions,
        invalidation_conditions=signal.invalidation_conditions,
        missing_information=(
            reason_codes if action == ActionType.WAIT_FOR_DATA else []
        ),
    )
