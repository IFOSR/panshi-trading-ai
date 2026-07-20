from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategy.context import StrategyContext


def evaluate(context: StrategyContext, strategy_enabled: bool) -> MilestoneResult:
    confirmed = strategy_enabled and context.price_confirmation
    return MilestoneResult(number=7, code="PRICE_CONFIRMATION",
                           status=MilestoneStatus.CONFIRMED if confirmed else MilestoneStatus.BLOCKED,
                           result="CONFIRMED" if confirmed else "PENDING", rule_ids=["PC-001"],
                           blockers=[] if confirmed else ["PRICE_NOT_CONFIRMED"],
                           next_conditions=[] if confirmed else ["等待执行周期价格确认"])
