from trading_agent.risk.engine import evaluate_risk
from trading_agent.risk.models import RiskContext


def test_unclosed_bar_and_rollover_veto_risk() -> None:
    result = evaluate_risk(
        RiskContext(
            state_bar_closed=False,
            rollover_active=True,
            account_risk_limit=0.01,
            proposed_risk=0.005,
        )
    )

    assert result.status == "VETO"
    assert {"UNCLOSED_STATE_BAR", "ROLLOVER_ACTIVE"} <= set(result.reason_codes)


def test_missing_account_risk_blocks_sizing() -> None:
    result = evaluate_risk(RiskContext())

    assert result.status == "BLOCKED"
    assert "ACCOUNT_RISK_UNKNOWN" in result.reason_codes
