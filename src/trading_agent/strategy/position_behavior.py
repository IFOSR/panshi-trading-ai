from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategy.context import StrategyContext


def evaluate(context: StrategyContext) -> MilestoneResult:
    if context.open_interest_change is None:
        result, status, blockers = "UNKNOWN", MilestoneStatus.BLOCKED, ["OPEN_INTEREST_MISSING"]
    else:
        result, status, blockers = (
            "TOTAL_OPEN_INTEREST_INCREASED" if context.open_interest_change > 0
            else "TOTAL_OPEN_INTEREST_DECREASED" if context.open_interest_change < 0
            else "TOTAL_OPEN_INTEREST_FLAT",
            MilestoneStatus.CONFIRMED,
            [],
        )
    return MilestoneResult(number=5, code="POSITION_BEHAVIOR", status=status, result=result,
                           rule_ids=["PB-001"], blockers=blockers,
                           details={"volume_state": context.volume_state})
