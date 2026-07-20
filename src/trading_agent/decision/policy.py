from pydantic import BaseModel

from trading_agent.domain.decision import ActionDecision
from trading_agent.domain.enums import (
    ActionType, MarketState, MilestoneStatus, PositionDirection,
)
from trading_agent.domain.milestone import StrategyEvaluation
from trading_agent.risk.models import RiskResult
from trading_agent.strategy.context import StrategyContext


class DecisionInput(BaseModel):
    evaluation: StrategyEvaluation
    context: StrategyContext
    risk: RiskResult
    forced_exit: bool = False
    position_invalidated: bool = False
    reduce_required: bool = False
    add_confirmation: bool = False


def _market_state(result: str) -> MarketState:
    if result == "T+":
        return MarketState.T_PLUS
    if result == "T-":
        return MarketState.T_MINUS
    if result == "R":
        return MarketState.RANGE
    return MarketState.U


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
    } and item.risk.status == "APPROVED":
        action = ActionType.ADD_CONDITIONAL
    elif (
        position == PositionDirection.FLAT
        and strategy
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
        blocking = []
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
        next_milestone="补齐阻断数据" if action == ActionType.WAIT_FOR_DATA else "等待下一次价格确认",
        upgrade_conditions=["数据有效、价格确认且风险通过"],
        invalidation_conditions=["结构失效或风险引擎否决"],
        missing_information=reason_codes if action == ActionType.WAIT_FOR_DATA else [],
    )
