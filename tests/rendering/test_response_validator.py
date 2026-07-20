from trading_agent.decision.policy import decide_action
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
