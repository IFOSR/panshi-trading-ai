from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategy.context import StrategyContext


def evaluate(context: StrategyContext) -> MilestoneResult:
    blockers = []
    if not context.contract:
        blockers.append("CONTRACT_MISSING")
    if not context.timeframe:
        blockers.append("TIMEFRAME_MISSING")
    if context.state_bar_closed is not True:
        blockers.append("UNCLOSED_STATE_BAR")
    return MilestoneResult(
        number=1,
        code="DATA_VALIDITY",
        status=MilestoneStatus.BLOCKED if blockers else MilestoneStatus.CONFIRMED,
        result="BLOCKED" if blockers else "VALID",
        rule_ids=["DQ-001"],
        evidence_refs=context.evidence_refs,
        blockers=blockers,
        next_conditions=["确认真实合约、周期和状态周期收盘"] if blockers else [],
    )
