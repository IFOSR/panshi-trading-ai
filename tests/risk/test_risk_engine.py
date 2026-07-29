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


def test_excess_position_risk_requests_reduction_instead_of_veto() -> None:
    result = evaluate_risk(
        RiskContext(
            account_risk_limit=0.01,
            proposed_risk=0.02,
            correlated_exposure_exceeded=True,
        )
    )

    assert result.status == "REDUCE_REQUIRED"
    assert {"RISK_LIMIT_EXCEEDED", "CORRELATED_EXPOSURE"} <= set(result.reason_codes)
