from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategy.context import StrategyContext, evidence_refs_for


def _enabled_strategy(market_state: str, price_location: str) -> str | None:
    return {
        ("T+", "ABOVE_BOLL_UPPER"): "TREND_BREAKOUT_LONG",
        ("T+", "BETWEEN_UPPER_AND_MID"): "TREND_PULLBACK_LONG",
        ("T-", "BELOW_BOLL_LOWER"): "TREND_BREAKOUT_SHORT",
        ("T-", "BELOW_BOLL_MID_ABOVE_LOWER"): "TREND_PULLBACK_SHORT",
        ("R", "AT_RANGE_SUPPORT"): "RANGE_REVERSAL_LONG",
        ("R", "AT_RANGE_RESISTANCE"): "RANGE_REVERSAL_SHORT",
    }.get((market_state, price_location))


def evaluate(context: StrategyContext, market_state: str, data_valid: bool) -> MilestoneResult:
    strategy = _enabled_strategy(market_state, context.price_location)
    blockers = [] if strategy else ["NO_ENABLED_STRATEGY"]
    status = (
        MilestoneStatus.CONFIRMED
        if data_valid and strategy
        else MilestoneStatus.BLOCKED
        if not data_valid
        else MilestoneStatus.CANDIDATE
    )
    return MilestoneResult(
        number=3,
        code="STRATEGY_PERMISSION",
        status=status,
        result=strategy or "NONE",
        rule_ids=["SP-001"],
        evidence_refs=evidence_refs_for(context, "trend_score", "price_location"),
        blockers=blockers,
        next_conditions=(
            ["先解除第1步数据有效性阻断"]
            if not data_valid
            else ["等待市场状态进入可交易结构"]
            if blockers
            else []
        ),
        details={
            "market_state": market_state,
            "price_location": context.price_location,
        },
    )
