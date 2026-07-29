from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategy.context import StrategyContext, evidence_refs_for


def evaluate(context: StrategyContext) -> MilestoneResult:
    known = context.price_location != "UNKNOWN"
    return MilestoneResult(
        number=4, code="PRICE_LOCATION",
        status=MilestoneStatus.CONFIRMED if known else MilestoneStatus.BLOCKED,
        result=context.price_location, rule_ids=["PL-001"],
        evidence_refs=evidence_refs_for(context, "price_location"),
        blockers=[] if known else ["PRICE_LOCATION_UNKNOWN"],
    )
