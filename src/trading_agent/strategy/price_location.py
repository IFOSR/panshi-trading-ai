from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategy.context import StrategyContext


def evaluate(context: StrategyContext) -> MilestoneResult:
    known = context.price_location != "UNKNOWN"
    return MilestoneResult(
        number=4, code="PRICE_LOCATION",
        status=MilestoneStatus.CONFIRMED if known else MilestoneStatus.BLOCKED,
        result=context.price_location, rule_ids=["PL-001"],
        blockers=[] if known else ["PRICE_LOCATION_UNKNOWN"],
    )
