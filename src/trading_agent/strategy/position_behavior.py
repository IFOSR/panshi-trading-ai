from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategy.context import StrategyContext, evidence_refs_for


def evaluate(context: StrategyContext) -> MilestoneResult:
    if context.open_interest_change is None:
        has_visual_evidence = (
            context.position_behavior_state != "UNKNOWN"
            or context.volume_state != "UNKNOWN"
        )
        result = (
            context.position_behavior_state
            if context.position_behavior_state != "UNKNOWN"
            else context.volume_state
        )
        status = MilestoneStatus.CANDIDATE if has_visual_evidence else MilestoneStatus.BLOCKED
        blockers = ["OPEN_INTEREST_MISSING"]
    else:
        result, status, blockers = (
            "TOTAL_OPEN_INTEREST_INCREASED" if context.open_interest_change > 0
            else "TOTAL_OPEN_INTEREST_DECREASED" if context.open_interest_change < 0
            else "TOTAL_OPEN_INTEREST_FLAT",
            MilestoneStatus.CONFIRMED,
            [],
        )
    return MilestoneResult(number=5, code="POSITION_BEHAVIOR", status=status, result=result,
                           rule_ids=["PB-001"],
                           evidence_refs=evidence_refs_for(
                               context,
                               "open_interest_change",
                               "volume_state",
                               "position_behavior",
                           ),
                           blockers=blockers,
                           details={
                               "volume_state": context.volume_state,
                               "visual_position_behavior": context.position_behavior_state,
                           })
