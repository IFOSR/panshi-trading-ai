from trading_agent.risk.models import RiskContext, RiskResult


def evaluate_risk(context: RiskContext) -> RiskResult:
    vetoes = []
    blockers = []
    if context.state_bar_closed is False:
        vetoes.append("UNCLOSED_STATE_BAR")
    if context.contract_mismatch:
        vetoes.append("CONTRACT_MISMATCH")
    if context.rollover_active:
        vetoes.append("ROLLOVER_ACTIVE")
    if context.near_price_limit:
        vetoes.append("PRICE_LIMIT_NEAR")
    if context.correlated_exposure_exceeded:
        vetoes.append("CORRELATED_EXPOSURE")
    if context.stop_distance_ratio is not None and (
        context.stop_distance_ratio > context.max_stop_distance_ratio
    ):
        vetoes.append("STOP_DISTANCE_EXCESSIVE")
    if context.account_risk_limit is None:
        blockers.append("ACCOUNT_RISK_UNKNOWN")
    if context.proposed_risk is None:
        blockers.append("PROPOSED_RISK_UNKNOWN")
    elif (
        context.account_risk_limit is not None
        and context.proposed_risk > context.account_risk_limit
    ):
        vetoes.append("RISK_LIMIT_EXCEEDED")
    if not context.market_state_known:
        blockers.append("MARKET_STATE_UNKNOWN")
    if vetoes:
        return RiskResult(status="VETO", reason_codes=vetoes)
    if blockers:
        return RiskResult(status="BLOCKED", reason_codes=blockers)
    return RiskResult(status="APPROVED")
