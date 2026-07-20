from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult, StrategyEvaluation
from trading_agent.strategy import (
    data_validity, market_state, momentum, position_behavior, price_confirmation,
    price_location, strategy_permission,
)
from trading_agent.strategy.context import StrategyContext


def evaluate_strategy(context: StrategyContext) -> StrategyEvaluation:
    step1 = data_validity.evaluate(context)
    step2 = market_state.evaluate(context)
    step3 = strategy_permission.evaluate(
        context, step2.result, step1.status == MilestoneStatus.CONFIRMED
    )
    steps = [
        step1, step2, step3, price_location.evaluate(context),
        position_behavior.evaluate(context), momentum.evaluate(context),
        price_confirmation.evaluate(context, step3.status == MilestoneStatus.CONFIRMED),
    ]
    risk_ok = context.risk_status == "APPROVED"
    steps.append(MilestoneResult(
        number=8, code="RISK_AND_ACTION",
        status=MilestoneStatus.CONFIRMED if risk_ok else MilestoneStatus.BLOCKED,
        result=context.risk_status, rule_ids=["RK-001"],
        blockers=[] if risk_ok else [f"RISK_{context.risk_status}"],
    ))
    return StrategyEvaluation(steps=steps)
