from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategy.context import StrategyContext


def evaluate(context: StrategyContext, market_state: str, data_valid: bool) -> MilestoneResult:
    strategy = {
        "T+": "TREND_PULLBACK_LONG",
        "T-": "TREND_PULLBACK_SHORT",
        "R": "RANGE_REVERSAL",
    }.get(market_state)
    blockers = [] if data_valid and strategy else ["NO_ENABLED_STRATEGY"]
    return MilestoneResult(
        number=3,
        code="STRATEGY_PERMISSION",
        status=MilestoneStatus.CONFIRMED if not blockers else MilestoneStatus.BLOCKED,
        result=strategy or "NONE",
        rule_ids=["SP-001"],
        blockers=blockers,
        next_conditions=["等待市场状态进入可交易结构"] if blockers else [],
    )
