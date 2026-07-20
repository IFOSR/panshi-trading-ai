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
