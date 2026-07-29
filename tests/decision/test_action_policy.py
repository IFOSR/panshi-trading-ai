from trading_agent.decision.policy import DecisionInput, decide_action
from trading_agent.domain.enums import ActionType, PositionDirection
from trading_agent.risk.models import RiskResult
from tests.factories import make_confirmed_decision_input


def confirmed_input(**overrides: object) -> DecisionInput:
    return make_confirmed_decision_input(**overrides)


def test_data_blocker_prevents_entry() -> None:
    decision = decide_action(confirmed_input(contract=None))

    assert decision.action == ActionType.WAIT_FOR_DATA


def test_risk_veto_overrides_confirmed_entry() -> None:
    item = confirmed_input()
    item.risk = RiskResult(status="VETO", reason_codes=["PRICE_LIMIT_NEAR"])

    decision = decide_action(item)

    assert decision.action == ActionType.WAIT_FOR_SETUP
    assert 8 in decision.blocking_steps
    assert 8 not in decision.supporting_steps


def test_forced_exit_has_highest_precedence() -> None:
    item = confirmed_input(position=PositionDirection.LONG)
    item.forced_exit = True

    assert decide_action(item).action == ActionType.EXIT


def test_confirmed_flat_setup_can_only_enter_conditionally() -> None:
    decision = decide_action(confirmed_input())

    assert decision.action == ActionType.ENTER_CONDITIONAL
    assert {1, 2, 3, 7, 8} <= set(decision.supporting_steps)


def test_invalidated_open_position_exits_even_when_new_risk_is_blocked() -> None:
    item = confirmed_input(position=PositionDirection.LONG)
    item.position_invalidated = True
    item.risk = RiskResult(status="BLOCKED", reason_codes=["ACCOUNT_RISK_UNKNOWN"])

    assert decide_action(item).action == ActionType.EXIT


def test_reducible_risk_veto_reduces_an_existing_position() -> None:
    item = confirmed_input(position=PositionDirection.SHORT)
    item.reduce_required = True
    item.risk = RiskResult(
        status="REDUCE_REQUIRED",
        reason_codes=["RISK_LIMIT_EXCEEDED"],
    )

    assert decide_action(item).action == ActionType.REDUCE


def test_non_reducible_risk_veto_still_blocks_position_action() -> None:
    item = confirmed_input(position=PositionDirection.SHORT)
    item.reduce_required = True
    item.risk = RiskResult(
        status="VETO",
        reason_codes=["PRICE_LIMIT_NEAR", "RISK_LIMIT_EXCEEDED"],
    )

    assert decide_action(item).action == ActionType.WAIT_FOR_SETUP


def test_add_confirmation_degrades_safely_when_strategy_steps_are_blocked() -> None:
    item = confirmed_input(
        position=PositionDirection.SHORT,
        open_interest_change=None,
        position_behavior_state="UNKNOWN",
        momentum_state="UNKNOWN",
    )
    item.add_confirmation = True

    decision = decide_action(item)

    assert decision.action == ActionType.HOLD
    assert {5, 6} <= set(decision.blocking_steps)


def test_next_milestone_points_to_the_first_actual_blocked_strategy_step() -> None:
    item = confirmed_input(
        open_interest_change=None,
        position_behavior_state="UNKNOWN",
        momentum_state="UNKNOWN",
    )

    decision = decide_action(item)

    assert decision.action == ActionType.WAIT_FOR_SETUP
    assert decision.next_milestone == "补齐第5步：量仓行为"
