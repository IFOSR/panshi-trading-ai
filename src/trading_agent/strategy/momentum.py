from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategy.context import StrategyContext, evidence_refs_for


def evaluate(context: StrategyContext) -> MilestoneResult:
    known = context.momentum_state != "UNKNOWN"
    return MilestoneResult(number=6, code="MOMENTUM",
                           status=MilestoneStatus.CANDIDATE if known else MilestoneStatus.BLOCKED,
                           result=context.momentum_state, rule_ids=["MO-001"],
                           evidence_refs=evidence_refs_for(context, "momentum_state"),
                           blockers=[] if known else ["MOMENTUM_UNKNOWN"])
