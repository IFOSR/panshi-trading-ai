from datetime import datetime
from zoneinfo import ZoneInfo

from trading_agent.domain.enums import EvidenceUsage, PositionDirection
from trading_agent.domain.evidence import (
    Evidence,
    FactSupport,
    ScreenshotEvidence,
    StrategyEvidenceFacts,
)
from trading_agent.strategy.context_builder import build_strategy_context
from trading_agent.strategy import data_validity


def make_evidence(
    *,
    role: str = "STATE_DAILY",
    timeframe: str = "1d",
    contract: str | None = "rb2610",
    trend_score: int | None = None,
    latest_close: float | None = None,
    cutoff_time: str | None = "2026-07-20",
    facts: StrategyEvidenceFacts | None = None,
) -> ScreenshotEvidence:
    resolved_facts = facts or StrategyEvidenceFacts()
    fact_values = resolved_facts.model_dump()
    supported_fields = {
        key: value
        for key, value in fact_values.items()
        if value not in {"UNKNOWN", None, False}
        and key
        in {
            "trend_bias",
            "price_location",
            "volume_state",
            "momentum_state",
            "position_behavior",
            "price_confirmation",
            "price_confirmation_direction",
            "price_confirmation_type",
        }
    }
    observations = [
        Evidence(
            evidence_id=f"support-{key}",
            kind=key,
            value=value,
            confidence=0.95,
            provenance="codex:gpt-5.6-sol",
        )
        for key, value in supported_fields.items()
    ]
    return ScreenshotEvidence(
        image_role=role,
        provider="codex",
        model="gpt-5.6-sol",
        prompt_version="chart-evidence-v2",
        image_sha256=f"hash-{role}",
        contract=contract,
        timeframe=timeframe,
        trend_score=trend_score,
        latest_close=latest_close,
        cutoff_time=cutoff_time,
        last_bar_closed=True,
        strategy_facts=resolved_facts,
        observations=observations,
        strategy_fact_support={
            key: FactSupport(
                confidence=0.95,
                evidence_refs=[f"support-{key}"],
            )
            for key in supported_fields
        },
    )


def test_daily_visual_facts_feed_price_volume_and_momentum_steps() -> None:
    evidence = make_evidence(
        facts=StrategyEvidenceFacts(
            trend_bias="BEARISH",
            price_location="BELOW_BOLL_MID_ABOVE_LOWER",
            volume_state="BELOW_BOTH_AVERAGES",
            momentum_state="BEARISH_RECOVERY",
            position_behavior="LONG_BUILD_SHORT_COVER",
        )
    )

    context = build_strategy_context(
        [evidence],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
    )

    assert context.trend_score == -1
    assert context.price_location == "BELOW_BOLL_MID_ABOVE_LOWER"
    assert context.volume_state == "BELOW_BOTH_AVERAGES"
    assert context.momentum_state == "BEARISH_RECOVERY"
    assert context.position_behavior_state == "LONG_BUILD_SHORT_COVER"


def test_structured_market_data_audit_reaches_data_validity_milestone() -> None:
    evidence = make_evidence(contract="rb2610").model_copy(
        update={
            "market_data_sources": ["tqsdk"],
            "market_data_validation_sources": ["SHFE_OFFICIAL_DAILY"],
            "market_data_quality_issues": ["WAREHOUSE_DATA_UNAVAILABLE"],
        }
    )

    context = build_strategy_context(
        [evidence],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 20, 16, 0, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )
    result = data_validity.evaluate(context)

    assert context.market_data_sources == ["tqsdk"]
    assert context.market_data_validation_sources == ["SHFE_OFFICIAL_DAILY"]
    assert context.market_data_quality_issues == ["WAREHOUSE_DATA_UNAVAILABLE"]
    assert result.details == {
        "contract": "rb2610",
        "timeframe": "1d",
        "cutoff_time": "2026-07-20",
        "last_bar_closed": True,
        "data_age_seconds": 0.0,
        "sources": ["tqsdk"],
        "validation_sources": ["SHFE_OFFICIAL_DAILY"],
        "quality_issues": ["WAREHOUSE_DATA_UNAVAILABLE"],
        "contract_metadata": {},
    }


def test_price_confirmation_only_comes_from_execution_role() -> None:
    daily = make_evidence(
        facts=StrategyEvidenceFacts(
            price_confirmation=True,
            price_confirmation_direction="BEARISH",
            price_confirmation_type="PULLBACK",
        ),
    )
    execution = make_evidence(
        role="EXECUTION_60M",
        timeframe="60m",
        cutoff_time="2026-07-20T10:00:00+08:00",
        facts=StrategyEvidenceFacts(
            price_confirmation=True,
            price_confirmation_direction="BEARISH",
            price_confirmation_type="PULLBACK",
        ),
    )

    daily_only = build_strategy_context(
        [daily],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
    )
    with_execution = build_strategy_context(
        [daily, execution],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert daily_only.price_confirmation is None
    assert with_execution.price_confirmation is True


def test_structured_negative_execution_confirmation_remains_known() -> None:
    daily = make_evidence()
    execution = make_evidence(
        role="EXECUTION_60M",
        timeframe="60m",
        cutoff_time="2026-07-20T10:00:00+08:00",
        facts=StrategyEvidenceFacts(
            price_confirmation=False,
        ),
    ).model_copy(
        update={
            "field_provenance": {
                "strategy_facts.price_confirmation": "structured_market_data",
            },
        }
    )

    context = build_strategy_context(
        [daily, execution],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert context.price_confirmation is False


def test_date_only_execution_cutoff_cannot_confirm_an_intraday_signal() -> None:
    daily = make_evidence()
    execution = make_evidence(
        role="EXECUTION_60M",
        timeframe="60m",
        cutoff_time="2026-07-20",
        facts=StrategyEvidenceFacts(
            price_confirmation=True,
            price_confirmation_direction="BEARISH",
            price_confirmation_type="PULLBACK",
        ),
    )

    context = build_strategy_context(
        [daily, execution],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
    )

    assert context.price_confirmation is None
    assert "EXECUTION_CUTOFF_TIME_MISSING" in context.data_blockers


def test_current_trading_date_daily_bar_is_unclosed_before_session_close() -> None:
    context = build_strategy_context(
        [make_evidence(cutoff_time="2026-07-20")],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 20, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert context.state_bar_closed is False
    assert "CURRENT_TRADING_DATE_UNCLOSED" in context.data_blockers


def test_future_cutoffs_block_state_and_execution_evidence() -> None:
    daily = make_evidence(
        cutoff_time="2026-07-20T12:00:00+08:00",
        trend_score=-3,
        facts=StrategyEvidenceFacts(
            trend_bias="BEARISH",
            price_location="BELOW_BOLL_LOWER",
        ),
    )
    execution = make_evidence(
        role="EXECUTION_60M",
        timeframe="60m",
        cutoff_time="2026-07-20T12:00:00+08:00",
        facts=StrategyEvidenceFacts(
            price_confirmation=True,
            price_confirmation_direction="BEARISH",
            price_confirmation_type="BREAKOUT",
        ),
    )

    context = build_strategy_context(
        [daily, execution],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert "CUTOFF_IN_FUTURE" in context.data_blockers
    assert "EXECUTION_CUTOFF_IN_FUTURE" in context.data_blockers
    assert context.price_confirmation is None


def test_latest_friday_market_data_remains_fresh_during_weekend() -> None:
    daily = make_evidence(
        cutoff_time="2026-07-24T15:00:00+08:00",
    )
    execution = make_evidence(
        role="EXECUTION_60M",
        timeframe="60m",
        cutoff_time="2026-07-24T23:00:00+08:00",
    )

    context = build_strategy_context(
        [daily, execution],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 26, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert "DATA_STALE" not in context.data_blockers
    assert "EXECUTION_DATA_STALE" not in context.data_blockers
    assert data_validity.evaluate(context).blockers == []


def test_latest_friday_daily_data_remains_fresh_before_monday_close() -> None:
    daily = make_evidence(
        cutoff_time="2026-07-24T15:00:00+08:00",
    )

    context = build_strategy_context(
        [daily],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 27, 11, 15, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert "DATA_STALE" not in context.data_blockers
    assert data_validity.evaluate(context).blockers == []


def test_data_older_than_latest_friday_is_stale_during_weekend() -> None:
    daily = make_evidence(
        cutoff_time="2026-07-23T15:00:00+08:00",
    )
    execution = make_evidence(
        role="EXECUTION_60M",
        timeframe="60m",
        cutoff_time="2026-07-23T23:00:00+08:00",
    )

    context = build_strategy_context(
        [daily, execution],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 26, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert "DATA_STALE" in context.data_blockers
    assert "EXECUTION_DATA_STALE" in context.data_blockers


def test_stale_execution_confirmation_is_not_consumed() -> None:
    daily = make_evidence(
        cutoff_time="2026-07-24T15:00:00+08:00",
    )
    execution = make_evidence(
        role="EXECUTION_60M",
        timeframe="60m",
        cutoff_time="2026-07-24T23:00:00+08:00",
        facts=StrategyEvidenceFacts(
            price_confirmation=True,
            price_confirmation_direction="BEARISH",
            price_confirmation_type="PULLBACK",
        ),
    )

    context = build_strategy_context(
        [daily, execution],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 27, 11, 15, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert "EXECUTION_DATA_STALE" in context.data_blockers
    assert context.price_confirmation is None
    assert context.price_confirmation_direction == "UNKNOWN"
    assert context.price_confirmation_type == "UNKNOWN"


def test_unclosed_execution_confirmation_remains_unknown() -> None:
    daily = make_evidence()
    execution = make_evidence(
        role="EXECUTION_60M",
        timeframe="60m",
        cutoff_time="2026-07-20T10:30:00+08:00",
        facts=StrategyEvidenceFacts(price_confirmation=False),
    ).model_copy(
        update={
            "last_bar_closed": False,
            "field_provenance": {
                "strategy_facts.price_confirmation": "structured_market_data",
            },
        }
    )

    context = build_strategy_context(
        [daily, execution],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert context.price_confirmation is None


def test_thursday_daily_data_is_stale_early_saturday() -> None:
    context = build_strategy_context(
        [
            make_evidence(
                cutoff_time="2026-07-23T15:00:00+08:00",
            )
        ],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 25, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert "DATA_STALE" in context.data_blockers


def test_blocked_evidence_usage_cannot_advance_strategy_context() -> None:
    blocked = make_evidence(
        trend_score=-3,
        facts=StrategyEvidenceFacts(
            trend_bias="BEARISH",
            price_location="BELOW_BOLL_LOWER",
        ),
    ).model_copy(
        update={
            "allowed_usage": EvidenceUsage.BLOCKED,
            "blocking_issues": [],
        }
    )

    context = build_strategy_context(
        [blocked],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
    )

    assert "EVIDENCE_USAGE_BLOCKED" in context.data_blockers
    assert context.trend_score == 0
    assert context.price_location == "UNKNOWN"


def test_daily_chart_role_is_normalized_from_typed_visible_facts() -> None:
    evidence = make_evidence(
        role="AUXILIARY",
        facts=StrategyEvidenceFacts(
            price_location="BELOW_BOLL_MID_ABOVE_LOWER",
            momentum_state="BEARISH_RECOVERY",
        ),
    )

    context = build_strategy_context(
        [evidence],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
    )

    assert context.state_image_role == "STATE_DAILY"


def test_case_and_screenshot_contract_conflict_blocks_strategy_context() -> None:
    context = build_strategy_context(
        [make_evidence(contract="rb2605")],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
    )

    assert context.contract == "rb2610"
    assert "CONTRACT_CONFLICT" in context.data_blockers


def test_case_and_screenshot_contract_identity_ignores_case_and_whitespace() -> None:
    context = build_strategy_context(
        [make_evidence(contract=" CF2609 ")],
        case_contract="cf2609",
        position=PositionDirection.FLAT,
    )

    assert context.contract == "cf2609"
    assert "CONTRACT_CONFLICT" not in context.data_blockers
    assert context.contract_mismatch is False


def test_execution_contract_must_match_daily_contract() -> None:
    daily = make_evidence(
        contract="rb2610",
        trend_score=-3,
        facts=StrategyEvidenceFacts(
            trend_bias="BEARISH",
            price_location="BELOW_BOLL_LOWER",
        ),
    )
    execution = make_evidence(
        role="EXECUTION_60M",
        timeframe="60m",
        contract="cu2609",
        cutoff_time="2026-07-20T10:00:00+08:00",
        facts=StrategyEvidenceFacts(
            price_confirmation=True,
            price_confirmation_direction="BEARISH",
            price_confirmation_type="BREAKOUT",
        ),
    )

    context = build_strategy_context(
        [daily, execution],
        case_contract=None,
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert "CONTRACT_CONFLICT" in context.data_blockers
    assert context.price_confirmation is None
    assert context.price_confirmation_direction == "UNKNOWN"


def test_execution_confirmation_requires_a_contract_identity() -> None:
    daily = make_evidence(
        contract="rb2610",
        trend_score=-3,
        facts=StrategyEvidenceFacts(
            trend_bias="BEARISH",
            price_location="BELOW_BOLL_LOWER",
        ),
    )
    execution = make_evidence(
        role="EXECUTION_60M",
        timeframe="60m",
        contract=None,
        cutoff_time="2026-07-20T10:00:00+08:00",
        facts=StrategyEvidenceFacts(
            price_confirmation=True,
            price_confirmation_direction="BEARISH",
            price_confirmation_type="BREAKOUT",
        ),
    )

    context = build_strategy_context(
        [daily, execution],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert "EXECUTION_CONTRACT_MISSING" in context.data_blockers
    assert context.price_confirmation is None
    assert context.price_confirmation_direction == "UNKNOWN"


def test_case_risk_and_verified_market_facts_build_position_action_context() -> None:
    daily = make_evidence(
        contract="rb2610",
        trend_score=-3,
        latest_close=94,
        facts=StrategyEvidenceFacts(
            trend_bias="BEARISH",
            price_location="BELOW_BOLL_LOWER",
        ),
    )

    context = build_strategy_context(
        [daily],
        case_contract="rb2610",
        position=PositionDirection.LONG,
        case_state={
            "risk": {
                "account_risk_limit": 0.01,
                "proposed_risk": 0.005,
                "correlated_exposure_exceeded": False,
            },
            "position": {
                "direction": "LONG",
                "quantity": 2,
                "average_cost": 100,
                "stop_price": 95,
            },
        },
    )

    assert context.trend_score == -3
    assert context.account_risk_limit == 0.01
    assert context.proposed_risk == 0.005
    assert context.stop_distance_ratio == 0.05
    assert context.forced_exit is True
    assert context.position_invalidated is True


def test_execution_image_cannot_substitute_for_missing_daily_state_image() -> None:
    context = build_strategy_context(
        [
            make_evidence(
                role="EXECUTION_60M",
                timeframe="60m",
                contract="rb2610",
                facts=StrategyEvidenceFacts(price_confirmation=True),
            )
        ],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
    )

    assert context.state_image_role is None
    assert "STATE_IMAGE_MISSING" in context.data_blockers


def test_low_confidence_or_unlinked_model_fact_cannot_advance_strategy() -> None:
    evidence = make_evidence(
        facts=StrategyEvidenceFacts(
            trend_bias="BEARISH",
            price_location="BELOW_BOLL_LOWER",
        )
    ).model_copy(
        update={
            "observations": [
                Evidence(
                    evidence_id="price-1",
                    kind="price_location",
                    value="below lower",
                    confidence=0.95,
                    provenance="codex:gpt-5.6-sol",
                )
            ],
            "strategy_fact_support": {
                "trend_bias": FactSupport(
                    confidence=0.4,
                    evidence_refs=["price-1"],
                ),
                "price_location": FactSupport(
                    confidence=0.95,
                    evidence_refs=["missing-ref"],
                ),
            },
        }
    )

    context = build_strategy_context(
        [evidence],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
    )

    assert context.trend_score == 0
    assert context.price_location == "UNKNOWN"
    assert "TREND_BIAS_UNSUPPORTED" in context.data_blockers
    assert "PRICE_LOCATION_UNSUPPORTED" in context.data_blockers


def test_execution_confirmation_requires_supported_value_direction_and_type() -> None:
    daily = make_evidence(
        trend_score=-3,
        facts=StrategyEvidenceFacts(
            trend_bias="BEARISH",
            price_location="BELOW_BOLL_MID_ABOVE_LOWER",
        ),
    )
    unsupported_execution = make_evidence(
        role="EXECUTION_60M",
        timeframe="60m",
        facts=StrategyEvidenceFacts(
            price_confirmation=True,
            price_confirmation_direction="BEARISH",
            price_confirmation_type="PULLBACK",
        ),
    ).model_copy(
        update={
            "observations": [],
            "strategy_fact_support": {},
        }
    )

    context = build_strategy_context(
        [daily, unsupported_execution],
        case_contract="rb2610",
        position=PositionDirection.FLAT,
    )

    assert context.price_confirmation is None
    assert context.price_confirmation_direction == "UNKNOWN"
    assert context.price_confirmation_type == "UNKNOWN"
    assert {
        "PRICE_CONFIRMATION_UNSUPPORTED",
        "PRICE_CONFIRMATION_DIRECTION_UNSUPPORTED",
        "PRICE_CONFIRMATION_TYPE_UNSUPPORTED",
    } <= set(context.data_blockers)


def test_add_confirmation_requires_controlled_stop_and_new_execution_image() -> None:
    daily = make_evidence(
        contract="rb2610",
        trend_score=-3,
        facts=StrategyEvidenceFacts(
            trend_bias="BEARISH",
            price_location="BELOW_BOLL_MID_ABOVE_LOWER",
        ),
    )
    execution = make_evidence(
        role="EXECUTION_60M",
        timeframe="60m",
        cutoff_time="2026-07-20T10:00:00+08:00",
        facts=StrategyEvidenceFacts(
            price_confirmation=True,
            price_confirmation_direction="BEARISH",
            price_confirmation_type="PULLBACK",
        ),
    ).model_copy(update={"source_image_id": "execution-new"})
    case_state = {
        "risk": {
            "account_risk_limit": 0.01,
            "proposed_risk": 0.005,
        },
        "position": {
            "direction": "SHORT",
            "quantity": 1,
            "average_cost": 100,
        },
    }

    without_stop = build_strategy_context(
        [daily, execution],
        case_contract="rb2610",
        position=PositionDirection.SHORT,
        case_state=case_state,
        analysis_time=datetime(
            2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )
    controlled = build_strategy_context(
        [daily, execution],
        case_contract="rb2610",
        position=PositionDirection.SHORT,
        case_state={
            **case_state,
            "position": {
                **case_state["position"],
                "stop_price": 102,
            },
        },
        analysis_time=datetime(
            2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )
    repeated = build_strategy_context(
        [daily, execution],
        case_contract="rb2610",
        position=PositionDirection.SHORT,
        case_state={
            **case_state,
            "position": {
                **case_state["position"],
                "stop_price": 102,
            },
        },
        previous_evidence_set=[
            execution.model_dump(mode="json"),
        ],
        analysis_time=datetime(
            2026, 7, 20, 11, 0, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )

    assert without_stop.add_confirmation is False
    assert controlled.add_confirmation is True
    assert repeated.add_confirmation is False
