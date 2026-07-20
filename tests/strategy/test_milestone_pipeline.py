from trading_agent.domain.enums import MilestoneStatus, PositionDirection
from trading_agent.strategy.context import StrategyContext
from trading_agent.strategy.evaluator import evaluate_strategy


def test_bearish_transition_produces_eight_auditable_steps() -> None:
    result = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
            prior_market_state="R",
            trend_score=-1,
            price_location="BELOW_BOLL_MID",
            open_interest_change=-1000,
            volume_state="LOW",
            momentum_state="BEARISH_RECOVERY",
            price_confirmation=False,
            position=PositionDirection.FLAT,
        )
    )

    assert [step.number for step in result.steps] == list(range(1, 9))
    assert result.steps[1].result == "U_BEARISH_BIAS"
    assert result.steps[2].status == MilestoneStatus.BLOCKED
    assert all(step.rule_ids or step.blockers for step in result.steps)


def test_unclosed_state_bar_cannot_switch_market_state() -> None:
    result = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=False,
            prior_market_state="R",
            trend_score=-3,
            price_confirmation=True,
        )
    )

    assert result.steps[1].result == "R"
    assert "UNCLOSED_STATE_BAR" in result.steps[0].blockers


def test_momentum_alone_never_confirms_entry() -> None:
    result = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
            prior_market_state="T-",
            trend_score=-3,
            momentum_state="BULLISH_DIVERGENCE",
            price_confirmation=False,
        )
    )

    assert result.steps[6].status != MilestoneStatus.CONFIRMED
