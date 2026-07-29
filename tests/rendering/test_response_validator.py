from trading_agent.decision.policy import decide_action
from trading_agent.domain.enums import PositionDirection
from trading_agent.rendering.service import render_decision
from trading_agent.rendering.validator import validate_rendered_response
from tests.factories import make_confirmed_decision_input


def test_renderer_rejects_action_mismatch() -> None:
    decision = decide_action(make_confirmed_decision_input())
    result = validate_rendered_response(
        decision,
        {
            "action": "WAIT_FOR_SETUP",
            "supporting_steps": decision.supporting_steps,
            "blocking_steps": decision.blocking_steps,
            "upgrade_conditions": decision.upgrade_conditions,
            "invalidation_conditions": decision.invalidation_conditions,
            "next_milestone": decision.next_milestone,
            "data_limitations": [],
            "summary": "等待",
        },
    )

    assert not result.is_valid
    assert "ACTION_MISMATCH" in result.errors


def test_deterministic_renderer_contains_auditable_fields() -> None:
    decision = decide_action(make_confirmed_decision_input())
    rendered = render_decision(decision)

    assert rendered.action == decision.action
    assert rendered.supporting_steps == decision.supporting_steps
    assert rendered.invalidation_conditions == decision.invalidation_conditions


def test_unknown_position_renderer_has_empty_long_and_short_branches() -> None:
    decision_input = make_confirmed_decision_input(position=PositionDirection.UNKNOWN)
    decision = decide_action(decision_input)

    rendered = render_decision(decision)

    assert [branch.scope for branch in rendered.position_branches] == [
        PositionDirection.FLAT,
        PositionDirection.LONG,
        PositionDirection.SHORT,
    ]
    assert all(branch.action == decision.action for branch in rendered.position_branches)


def test_hold_guidance_does_not_request_already_defaulted_risk_inputs() -> None:
    decision = decide_action(
        make_confirmed_decision_input(position=PositionDirection.LONG)
    )

    rendered = render_decision(decision)

    assert rendered.position_branches[0].guidance == (
        "维持当前仓位，暂不加仓；监控结构失效条件与下一策略里程碑。"
    )


def test_entry_guidance_matches_the_enter_action() -> None:
    decision = decide_action(make_confirmed_decision_input())

    rendered = render_decision(decision)

    assert rendered.position_branches[0].guidance == (
        "策略条件与风险许可均已满足；按计划建立新仓，不追价。"
    )


def test_short_position_branch_is_not_labeled_as_flat() -> None:
    decision = decide_action(
        make_confirmed_decision_input(position=PositionDirection.SHORT)
    )

    rendered = render_decision(decision)

    assert rendered.position_branches[0].label == "空头持仓分支"
