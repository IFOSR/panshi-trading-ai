from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategy.context import StrategyContext


def evaluate(context: StrategyContext) -> MilestoneResult:
    blockers = list(context.data_blockers)
    if not context.contract:
        blockers.append("CONTRACT_MISSING")
    if not context.timeframe:
        blockers.append("TIMEFRAME_MISSING")
    if context.state_bar_closed is not True:
        blockers.append("UNCLOSED_STATE_BAR")
    if not context.data_cutoff_time or context.data_age_seconds is None:
        blockers.append("CUTOFF_MISSING")
    elif context.data_age_seconds > context.max_data_age_seconds:
        blockers.append("DATA_STALE")
    return MilestoneResult(
        number=1,
        code="DATA_VALIDITY",
        status=MilestoneStatus.BLOCKED if blockers else MilestoneStatus.CONFIRMED,
        result="BLOCKED" if blockers else "VALID",
        rule_ids=["DQ-001"],
        evidence_refs=context.evidence_refs,
        blockers=blockers,
        next_conditions=["确认真实合约、周期和状态周期收盘"] if blockers else [],
        details={
            "contract": context.contract,
            "timeframe": context.timeframe,
            "cutoff_time": context.data_cutoff_time,
            "last_bar_closed": context.state_bar_closed,
            "data_age_seconds": context.data_age_seconds,
            "sources": context.market_data_sources,
            "validation_sources": context.market_data_validation_sources,
            "quality_issues": context.market_data_quality_issues,
            "contract_metadata": context.market_contract_metadata,
        },
    )
