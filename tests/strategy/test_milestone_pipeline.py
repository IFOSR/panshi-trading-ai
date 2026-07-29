import pytest

from trading_agent.domain.enums import MilestoneStatus, PositionDirection
from trading_agent.strategy.context import StrategyContext
from trading_agent.strategy.evaluator import evaluate_strategy


def test_bearish_transition_produces_eight_auditable_steps() -> None:
    result = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
            data_cutoff_time="2026-07-20",
            data_age_seconds=0,
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
    assert result.steps[2].status == MilestoneStatus.CANDIDATE
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


def test_visual_volume_and_position_evidence_is_candidate_without_total_open_interest() -> None:
    result = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
            volume_state="BELOW_BOTH_AVERAGES",
            position_behavior_state="LONG_BUILD_SHORT_COVER",
        )
    )

    assert result.steps[4].status == MilestoneStatus.CANDIDATE
    assert result.steps[4].result == "LONG_BUILD_SHORT_COVER"
    assert "OPEN_INTEREST_MISSING" in result.steps[4].blockers


def test_price_confirmation_direction_must_match_enabled_short_strategy() -> None:
    mismatched = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
            data_cutoff_time="2026-07-20",
            data_age_seconds=0,
            max_data_age_seconds=129_600,
            trend_score=-3,
            price_location="BELOW_BOLL_LOWER",
            price_confirmation=True,
            price_confirmation_direction="BULLISH",
            price_confirmation_type="BREAKOUT",
        )
    )
    matched = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
            data_cutoff_time="2026-07-20",
            data_age_seconds=0,
            max_data_age_seconds=129_600,
            trend_score=-3,
            price_location="BELOW_BOLL_LOWER",
            price_confirmation=True,
            price_confirmation_direction="BEARISH",
            price_confirmation_type="BREAKOUT",
        )
    )

    assert mismatched.steps[6].status == MilestoneStatus.CANDIDATE
    assert "CONFIRMATION_DIRECTION_MISMATCH" in mismatched.steps[6].blockers
    assert matched.steps[6].status == MilestoneStatus.CONFIRMED
    assert matched.steps[6].blockers == []


def test_missing_or_stale_cutoff_blocks_data_validity() -> None:
    missing = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
        )
    )
    stale = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="60m",
            state_bar_closed=True,
            data_cutoff_time="2026-07-19T10:00:00+08:00",
            data_age_seconds=86_400,
            max_data_age_seconds=7_200,
        )
    )

    assert "CUTOFF_MISSING" in missing.steps[0].blockers
    assert "DATA_STALE" in stale.steps[0].blockers


@pytest.mark.parametrize(
    ("trend_score", "price_location", "expected_strategy"),
    [
        (3, "ABOVE_BOLL_UPPER", "TREND_BREAKOUT_LONG"),
        (3, "BETWEEN_UPPER_AND_MID", "TREND_PULLBACK_LONG"),
        (-3, "BELOW_BOLL_LOWER", "TREND_BREAKOUT_SHORT"),
        (-3, "BELOW_BOLL_MID_ABOVE_LOWER", "TREND_PULLBACK_SHORT"),
        (0, "AT_RANGE_SUPPORT", "RANGE_REVERSAL_LONG"),
        (0, "AT_RANGE_RESISTANCE", "RANGE_REVERSAL_SHORT"),
    ],
)
def test_all_approved_strategies_are_reachable(
    trend_score: int,
    price_location: str,
    expected_strategy: str,
) -> None:
    result = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
            data_cutoff_time="2026-07-20",
            data_age_seconds=0,
            trend_score=trend_score,
            price_location=price_location,
        )
    )

    assert result.steps[2].status == MilestoneStatus.CONFIRMED
    assert result.steps[2].result == expected_strategy


def test_confirmation_type_must_match_enabled_strategy_family() -> None:
    result = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
            data_cutoff_time="2026-07-20",
            data_age_seconds=0,
            trend_score=3,
            price_location="ABOVE_BOLL_UPPER",
            price_confirmation=True,
            price_confirmation_direction="BULLISH",
            price_confirmation_type="PULLBACK",
        )
    )

    assert result.steps[2].result == "TREND_BREAKOUT_LONG"
    assert result.steps[6].status == MilestoneStatus.CANDIDATE
    assert "CONFIRMATION_TYPE_MISMATCH" in result.steps[6].blockers


def test_known_negative_confirmation_is_not_a_data_blocker() -> None:
    result = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
            data_cutoff_time="2026-07-20",
            data_age_seconds=0,
            trend_score=-3,
            price_location="BELOW_BOLL_MID_ABOVE_LOWER",
            price_confirmation=False,
        )
    )

    confirmation = result.steps[6]
    assert confirmation.status == MilestoneStatus.CANDIDATE
    assert confirmation.result == "NOT_TRIGGERED"
    assert "PRICE_NOT_CONFIRMED" not in confirmation.blockers


def test_unknown_confirmation_remains_user_resolvable() -> None:
    result = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
            data_cutoff_time="2026-07-20",
            data_age_seconds=0,
            trend_score=-3,
            price_location="BELOW_BOLL_MID_ABOVE_LOWER",
            price_confirmation=None,
        )
    )

    confirmation = result.steps[6]
    assert confirmation.status == MilestoneStatus.BLOCKED
    assert confirmation.result == "UNKNOWN"
    assert confirmation.blockers == ["PRICE_NOT_CONFIRMED"]


def test_positive_confirmation_without_enabled_strategy_is_not_a_direction_mismatch() -> None:
    result = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
            data_cutoff_time="2026-07-20",
            data_age_seconds=0,
            trend_score=-1,
            price_location="BELOW_BOLL_MID_ABOVE_LOWER",
            price_confirmation=True,
            price_confirmation_direction="BULLISH",
            price_confirmation_type="PULLBACK",
        )
    )

    permission = result.steps[2]
    confirmation = result.steps[6]
    assert permission.status == MilestoneStatus.CANDIDATE
    assert permission.result == "NONE"
    assert confirmation.status == MilestoneStatus.CANDIDATE
    assert confirmation.result == "NOT_TRIGGERED"
    assert "CONFIRMATION_DIRECTION_MISMATCH" not in confirmation.blockers


def test_enabled_strategy_is_not_reported_as_missing_when_data_is_blocked() -> None:
    result = evaluate_strategy(
        StrategyContext(
            contract="cf2609",
            timeframe="1d",
            state_bar_closed=True,
            data_cutoff_time="2026-07-28T15:00:00+08:00",
            data_age_seconds=0,
            data_blockers=["AUTOMATIC_CUTOFF_RECHECK_REQUIRED"],
            trend_score=-3,
            price_location="BELOW_BOLL_MID_ABOVE_LOWER",
        )
    )

    permission = result.steps[2]
    assert permission.status == MilestoneStatus.BLOCKED
    assert permission.result == "TREND_PULLBACK_SHORT"
    assert "NO_ENABLED_STRATEGY" not in permission.blockers


def test_each_strategy_milestone_references_only_consumed_fields() -> None:
    result = evaluate_strategy(
        StrategyContext(
            contract="rb2610",
            timeframe="1d",
            state_bar_closed=True,
            data_cutoff_time="2026-07-20",
            data_age_seconds=0,
            trend_score=-3,
            price_location="BELOW_BOLL_MID_ABOVE_LOWER",
            open_interest_change=100,
            volume_state="BELOW_BOTH_AVERAGES",
            position_behavior_state="POSITION_BUILDING",
            momentum_state="BEARISH_STRENGTHENING",
            price_confirmation=True,
            price_confirmation_direction="BEARISH",
            price_confirmation_type="PULLBACK",
            evidence_refs_by_field={
                "trend_score": ["trend-ref"],
                "price_location": ["price-ref"],
                "open_interest_change": ["oi-ref"],
                "volume_state": ["volume-ref"],
                "position_behavior": ["position-ref"],
                "momentum_state": ["momentum-ref"],
                "price_confirmation": ["confirmation-ref"],
                "price_confirmation_direction": ["direction-ref"],
                "price_confirmation_type": ["type-ref"],
            },
        )
    )

    assert result.steps[2].evidence_refs == ["trend-ref", "price-ref"]
    assert result.steps[3].evidence_refs == ["price-ref"]
    assert result.steps[4].evidence_refs == [
        "oi-ref",
        "volume-ref",
        "position-ref",
    ]
    assert result.steps[5].evidence_refs == ["momentum-ref"]
    assert result.steps[6].evidence_refs == [
        "confirmation-ref",
        "direction-ref",
        "type-ref",
    ]
