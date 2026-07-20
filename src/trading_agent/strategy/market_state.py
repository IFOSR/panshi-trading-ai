from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategy.context import StrategyContext


def evaluate(context: StrategyContext) -> MilestoneResult:
    if context.state_bar_closed is not True:
        result = context.prior_market_state
    elif context.trend_score >= 2:
        result = "T+"
    elif context.trend_score <= -2:
        result = "T-"
    elif context.trend_score > 0:
        result = "U_BULLISH_BIAS"
    elif context.trend_score < 0:
        result = "U_BEARISH_BIAS"
    else:
        result = "R"
    return MilestoneResult(
        number=2,
        code="MARKET_STATE",
        status=MilestoneStatus.CONFIRMED,
        result=result,
        rule_ids=["MS-001"],
        evidence_refs=context.evidence_refs,
    )
