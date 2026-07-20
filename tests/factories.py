from trading_agent.decision.policy import DecisionInput
from trading_agent.domain.enums import PositionDirection
from trading_agent.risk.models import RiskResult
from trading_agent.strategy.context import StrategyContext
from trading_agent.strategy.evaluator import evaluate_strategy


def make_confirmed_decision_input(**overrides: object) -> DecisionInput:
    values: dict[str, object] = {
        "contract": "rb2610",
        "timeframe": "1d",
        "state_bar_closed": True,
        "prior_market_state": "T-",
        "trend_score": -3,
        "price_location": "PULLBACK_RESISTANCE",
        "open_interest_change": 1000,
        "momentum_state": "BEARISH_STRENGTHENING",
        "price_confirmation": True,
        "position": PositionDirection.FLAT,
    }
    values.update(overrides)
    context = StrategyContext.model_validate(values)
    return DecisionInput(
        evaluation=evaluate_strategy(context),
        context=context,
        risk=RiskResult(status="APPROVED"),
    )
