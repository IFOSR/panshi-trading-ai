from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from trading_agent.domain.contracts import contract_identity
from trading_agent.domain.enums import EvidenceUsage, PositionDirection
from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.strategy.context import StrategyContext


SHANGHAI = ZoneInfo("Asia/Shanghai")


def _cutoff_age_seconds(
    cutoff_time: str | None,
    *,
    analysis_time: datetime,
) -> float | None:
    if cutoff_time is None:
        return None
    normalized = cutoff_time.replace("/", "-")
    if len(normalized) == 10:
        cutoff_date = date.fromisoformat(normalized)
        if cutoff_date == analysis_time.date():
            return 0.0
        cutoff = datetime.combine(cutoff_date, time(15, 0), tzinfo=SHANGHAI)
    else:
        cutoff = datetime.fromisoformat(normalized)
        if cutoff.tzinfo is None:
            return None
        cutoff = cutoff.astimezone(SHANGHAI)
    return max(0.0, (analysis_time - cutoff).total_seconds())


def _cutoff_is_in_future(
    cutoff_time: str | None,
    *,
    analysis_time: datetime,
) -> bool:
    if cutoff_time is None:
        return False
    normalized = cutoff_time.replace("/", "-")
    if len(normalized) == 10:
        return date.fromisoformat(normalized) > analysis_time.date()
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return False
    return parsed.astimezone(SHANGHAI) > analysis_time


def _has_precise_cutoff_time(cutoff_time: str | None) -> bool:
    if cutoff_time is None:
        return False
    normalized = cutoff_time.replace("/", "-")
    if len(normalized) == 10:
        return False
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _is_latest_friday_weekend_carry(
    cutoff_time: str | None,
    *,
    analysis_time: datetime,
) -> bool:
    if cutoff_time is None or analysis_time.weekday() not in {5, 6}:
        return False
    normalized = cutoff_time.replace("/", "-")
    try:
        cutoff_date = (
            date.fromisoformat(normalized)
            if len(normalized) == 10
            else datetime.fromisoformat(normalized).date()
        )
    except ValueError:
        return False
    latest_friday = analysis_time.date() - timedelta(
        days=analysis_time.weekday() - 4
    )
    return cutoff_date == latest_friday


def _is_latest_friday_daily_carry(
    cutoff_time: str | None,
    *,
    analysis_time: datetime,
) -> bool:
    if _is_latest_friday_weekend_carry(
        cutoff_time,
        analysis_time=analysis_time,
    ):
        return True
    if analysis_time.weekday() != 0 or analysis_time.time() >= time(15, 0):
        return False
    normalized = cutoff_time.replace("/", "-") if cutoff_time else ""
    try:
        cutoff_date = (
            date.fromisoformat(normalized)
            if len(normalized) == 10
            else datetime.fromisoformat(normalized).date()
        )
    except ValueError:
        return False
    return cutoff_date == analysis_time.date() - timedelta(days=3)


def _date_only_daily_bar_is_unclosed(
    cutoff_time: str | None,
    *,
    analysis_time: datetime,
) -> bool:
    if cutoff_time is None:
        return False
    normalized = cutoff_time.replace("/", "-")
    if len(normalized) != 10:
        return False
    return (
        date.fromisoformat(normalized) == analysis_time.date()
        and analysis_time.timetz().replace(tzinfo=None) < time(15, 0)
    )


def normalized_role(evidence: ScreenshotEvidence) -> str:
    facts = evidence.strategy_facts
    has_daily_structure = (
        evidence.timeframe in {"1d", "D1"}
        and (
            facts.price_location != "UNKNOWN"
            or facts.momentum_state != "UNKNOWN"
            or bool(evidence.indicators.get("boll"))
        )
    )
    if evidence.image_role == "AUXILIARY" and has_daily_structure:
        return "STATE_DAILY"
    return evidence.image_role


def _fact_supported(evidence: ScreenshotEvidence, field: str) -> bool:
    if evidence.field_provenance.get(f"strategy_facts.{field}") in {
        "structured_market_data",
        "user_confirmed",
    }:
        return True
    support = evidence.strategy_fact_support.get(field)
    observation_ids = {item.evidence_id for item in evidence.observations}
    return bool(
        support
        and support.confidence >= 0.8
        and set(support.evidence_refs) <= observation_ids
    )


def _accepted_fact(evidence: ScreenshotEvidence, field: str, value: str) -> tuple[str, bool]:
    accepted = _fact_supported(evidence, field)
    return (value if accepted else "UNKNOWN"), accepted


def _refs_for_evidence_field(
    evidence: ScreenshotEvidence,
    field: str,
) -> list[str]:
    explicit = evidence.field_evidence_refs.get(field, [])
    if explicit:
        return explicit
    if field.startswith("strategy_facts."):
        support = evidence.strategy_fact_support.get(field.removeprefix("strategy_facts."))
        if support:
            return support.evidence_refs
    return []


def build_strategy_context(
    evidence_set: Sequence[ScreenshotEvidence],
    *,
    case_contract: str | None,
    position: PositionDirection,
    case_state: Mapping[str, object] | None = None,
    previous_evidence_set: Sequence[Mapping[str, object]] = (),
    analysis_time: datetime | None = None,
) -> StrategyContext:
    resolved_analysis_time = (analysis_time or datetime.now(SHANGHAI)).astimezone(
        SHANGHAI
    )
    normalized = [
        (normalized_role(item), item)
        for item in evidence_set
        if item.allowed_usage != EvidenceUsage.BLOCKED
    ]
    state = next(
        (item for role, item in reversed(normalized) if role == "STATE_DAILY"),
        None,
    )
    execution = next(
        (item for role, item in reversed(normalized) if role == "EXECUTION_60M"),
        None,
    )
    expected_contract = case_contract or (state.contract if state else None)
    execution_contract_missing = bool(
        execution and expected_contract and not execution.contract
    )
    execution_contract_conflict = bool(
        execution
        and expected_contract
        and execution.contract
        and contract_identity(execution.contract)
        != contract_identity(expected_contract)
    )
    if execution_contract_missing or execution_contract_conflict:
        execution = None
    refs = list(dict.fromkeys(
        ref.evidence_id for evidence in evidence_set for ref in evidence.observations
    ))
    state_trend_refs = (
        [
            *_refs_for_evidence_field(state, "trend_score"),
            *_refs_for_evidence_field(state, "strategy_facts.trend_bias"),
        ]
        if state
        else []
    )
    refs_by_field = {
        "trend_score": list(dict.fromkeys(state_trend_refs)),
        "price_location": (
            _refs_for_evidence_field(state, "strategy_facts.price_location")
            if state else []
        ),
        "open_interest_change": (
            _refs_for_evidence_field(state, "open_interest_change")
            if state else []
        ),
        "volume_state": (
            _refs_for_evidence_field(state, "strategy_facts.volume_state")
            if state else []
        ),
        "position_behavior": (
            _refs_for_evidence_field(state, "strategy_facts.position_behavior")
            if state else []
        ),
        "momentum_state": (
            _refs_for_evidence_field(state, "strategy_facts.momentum_state")
            if state else []
        ),
        "price_confirmation": (
            _refs_for_evidence_field(execution, "strategy_facts.price_confirmation")
            if execution else []
        ),
        "price_confirmation_direction": (
            _refs_for_evidence_field(
                execution, "strategy_facts.price_confirmation_direction"
            )
            if execution else []
        ),
        "price_confirmation_type": (
            _refs_for_evidence_field(
                execution, "strategy_facts.price_confirmation_type"
            )
            if execution else []
        ),
    }
    blockers = list(dict.fromkeys(
        issue for evidence in evidence_set for issue in evidence.blocking_issues
    ))
    if execution_contract_missing:
        blockers.append("EXECUTION_CONTRACT_MISSING")
    if execution_contract_conflict:
        blockers.append("CONTRACT_CONFLICT")
    if any(item.allowed_usage == EvidenceUsage.BLOCKED for item in evidence_set):
        blockers.append("EVIDENCE_USAGE_BLOCKED")
    if state is None:
        return StrategyContext(
            contract=case_contract,
            position=position,
            data_blockers=list(dict.fromkeys([*blockers, "STATE_IMAGE_MISSING"])),
            evidence_refs=refs,
            evidence_refs_by_field=refs_by_field,
        )

    facts = state.strategy_facts
    trend_bias, trend_supported = _accepted_fact(state, "trend_bias", facts.trend_bias)
    price_value, price_supported = _accepted_fact(
        state, "price_location", facts.price_location
    )
    volume_value, _ = _accepted_fact(state, "volume_state", facts.volume_state)
    momentum_value, _ = _accepted_fact(state, "momentum_state", facts.momentum_state)
    position_value_fact, _ = _accepted_fact(
        state, "position_behavior", facts.position_behavior
    )
    trend_score = state.trend_score
    if trend_score is None:
        trend_score = {
            "BULLISH": 1,
            "BEARISH": -1,
            "RANGE": 0,
            "UNKNOWN": 0,
        }[trend_bias]
    if (
        case_contract
        and state.contract
        and contract_identity(case_contract) != contract_identity(state.contract)
    ):
        blockers = list(dict.fromkeys([*blockers, "CONTRACT_CONFLICT"]))
    if facts.trend_bias != "UNKNOWN" and not trend_supported:
        blockers.append("TREND_BIAS_UNSUPPORTED")
    if facts.price_location != "UNKNOWN" and not price_supported:
        blockers.append("PRICE_LOCATION_UNSUPPORTED")
    state_age_seconds = _cutoff_age_seconds(
        state.cutoff_time,
        analysis_time=resolved_analysis_time,
    )
    daily_carry = _is_latest_friday_daily_carry(
        state.cutoff_time,
        analysis_time=resolved_analysis_time,
    )
    state_max_data_age_seconds = 259_200 if daily_carry else 129_600
    if state.cutoff_time is None:
        blockers.append("CUTOFF_MISSING")
    elif _cutoff_is_in_future(
        state.cutoff_time,
        analysis_time=resolved_analysis_time,
    ):
        blockers.append("CUTOFF_IN_FUTURE")
    elif state_age_seconds is None:
        blockers.append("CUTOFF_INVALID")
    elif (
        resolved_analysis_time.weekday() in {5, 6}
        and not daily_carry
    ) or state_age_seconds > state_max_data_age_seconds:
        blockers.append("DATA_STALE")
    state_bar_closed = state.last_bar_closed
    if (
        state.timeframe in {"1d", "D1"}
        and _date_only_daily_bar_is_unclosed(
            state.cutoff_time,
            analysis_time=resolved_analysis_time,
        )
    ):
        state_bar_closed = False
        blockers.append("CURRENT_TRADING_DATE_UNCLOSED")
    execution_age_seconds = None
    execution_data_fresh = False
    if execution:
        execution_age_seconds = _cutoff_age_seconds(
            execution.cutoff_time,
            analysis_time=resolved_analysis_time,
        )
        if execution.cutoff_time is None:
            blockers.append("EXECUTION_CUTOFF_MISSING")
        elif _cutoff_is_in_future(
            execution.cutoff_time,
            analysis_time=resolved_analysis_time,
        ):
            blockers.append("EXECUTION_CUTOFF_IN_FUTURE")
        elif not _has_precise_cutoff_time(execution.cutoff_time):
            blockers.append("EXECUTION_CUTOFF_TIME_MISSING")
        elif execution_age_seconds is None:
            blockers.append("EXECUTION_CUTOFF_INVALID")
        elif (
            (
                resolved_analysis_time.weekday() in {5, 6}
                and not _is_latest_friday_weekend_carry(
                    execution.cutoff_time,
                    analysis_time=resolved_analysis_time,
                )
            )
            or (
                execution_age_seconds > 7_200
                and not _is_latest_friday_weekend_carry(
                    execution.cutoff_time,
                    analysis_time=resolved_analysis_time,
                )
            )
        ):
            blockers.append("EXECUTION_DATA_STALE")
        else:
            execution_data_fresh = True
    persisted = case_state or {}
    risk = persisted.get("risk")
    risk_values = risk if isinstance(risk, Mapping) else {}
    position_value = persisted.get("position")
    position_values = position_value if isinstance(position_value, Mapping) else {}
    average_cost = position_values.get("average_cost")
    stop_price = position_values.get("stop_price")
    stop_distance_ratio = None
    if isinstance(average_cost, (int, float)) and isinstance(stop_price, (int, float)):
        if average_cost:
            stop_distance_ratio = abs(float(average_cost) - float(stop_price)) / abs(
                float(average_cost)
            )
    forced_exit = False
    if state.latest_close is not None and isinstance(stop_price, (int, float)):
        forced_exit = (
            position == PositionDirection.LONG and state.latest_close <= float(stop_price)
        ) or (
            position == PositionDirection.SHORT and state.latest_close >= float(stop_price)
        )
    position_invalidated = (
        position == PositionDirection.LONG and trend_score <= -2
    ) or (
        position == PositionDirection.SHORT and trend_score >= 2
    )
    account_risk_limit = risk_values.get("account_risk_limit")
    proposed_risk = risk_values.get("proposed_risk")
    correlated_exposure_exceeded = bool(
        risk_values.get("correlated_exposure_exceeded", False)
    )
    reduce_required = correlated_exposure_exceeded or bool(
        isinstance(account_risk_limit, (int, float))
        and isinstance(proposed_risk, (int, float))
        and proposed_risk > account_risk_limit
    )
    previous_execution_ids = {
        str(item.get("source_image_id"))
        for item in previous_evidence_set
        if item.get("image_role") == "EXECUTION_60M"
        and item.get("source_image_id")
    }
    controlled_stop = bool(
        isinstance(stop_price, (int, float))
        and stop_distance_ratio is not None
        and stop_distance_ratio <= float(
            risk_values.get("max_stop_distance_ratio", 0.03)
        )
    )
    new_execution_confirmation = bool(
        execution
        and execution.source_image_id
        and execution.source_image_id not in previous_execution_ids
    )
    add_confirmation = bool(
        execution
        and execution_data_fresh
        and _has_precise_cutoff_time(execution.cutoff_time)
        and not _cutoff_is_in_future(
            execution.cutoff_time,
            analysis_time=resolved_analysis_time,
        )
        and new_execution_confirmation
        and controlled_stop
        and execution.last_bar_closed is True
        and _fact_supported(execution, "price_confirmation")
        and _fact_supported(execution, "price_confirmation_direction")
        and _fact_supported(execution, "price_confirmation_type")
        and execution.strategy_facts.price_confirmation is True
        and (
            (position == PositionDirection.LONG and trend_score > 0)
            or (position == PositionDirection.SHORT and trend_score < 0)
        )
    )
    execution_confirmation_supported = bool(
        execution
        and _fact_supported(execution, "price_confirmation")
    )
    execution_direction_supported = bool(
        execution
        and _fact_supported(execution, "price_confirmation_direction")
    )
    execution_type_supported = bool(
        execution
        and _fact_supported(execution, "price_confirmation_type")
    )
    if execution and execution.strategy_facts.price_confirmation is not None:
        if not execution_confirmation_supported:
            blockers.append("PRICE_CONFIRMATION_UNSUPPORTED")
        if (
            execution.strategy_facts.price_confirmation_direction != "UNKNOWN"
            and not execution_direction_supported
        ):
            blockers.append("PRICE_CONFIRMATION_DIRECTION_UNSUPPORTED")
        if (
            execution.strategy_facts.price_confirmation_type != "UNKNOWN"
            and not execution_type_supported
        ):
            blockers.append("PRICE_CONFIRMATION_TYPE_UNSUPPORTED")
    price_confirmation: bool | None = None
    execution_cutoff_usable = bool(
        execution
        and execution_data_fresh
        and execution.last_bar_closed is True
        and _has_precise_cutoff_time(execution.cutoff_time)
        and not _cutoff_is_in_future(
            execution.cutoff_time,
            analysis_time=resolved_analysis_time,
        )
    )
    if execution and execution_cutoff_usable:
        if execution_confirmation_supported:
            raw_confirmation = execution.strategy_facts.price_confirmation
            if raw_confirmation is False:
                price_confirmation = False
            elif (
                raw_confirmation is True
                and execution_direction_supported
                and execution_type_supported
            ):
                price_confirmation = True
    return StrategyContext(
        contract=case_contract or state.contract,
        timeframe=state.timeframe,
        state_bar_closed=state_bar_closed,
        data_cutoff_time=state.cutoff_time,
        data_age_seconds=state_age_seconds,
        max_data_age_seconds=state_max_data_age_seconds,
        trend_score=trend_score,
        price_location=price_value,
        open_interest_change=state.open_interest_change,
        volume_state=volume_value,
        position_behavior_state=position_value_fact,
        momentum_state=momentum_value,
        price_confirmation=price_confirmation,
        price_confirmation_direction=(
            execution.strategy_facts.price_confirmation_direction
            if execution
            and execution_cutoff_usable
            and execution_direction_supported
            else "UNKNOWN"
        ),
        price_confirmation_type=(
            execution.strategy_facts.price_confirmation_type
            if execution
            and execution_cutoff_usable
            and execution_type_supported
            else "UNKNOWN"
        ),
        position=position,
        state_image_role=normalized_role(state),
        data_blockers=blockers,
        evidence_refs=refs,
        evidence_refs_by_field=refs_by_field,
        market_data_sources=state.market_data_sources,
        market_data_validation_sources=state.market_data_validation_sources,
        market_data_quality_issues=state.market_data_quality_issues,
        market_contract_metadata=state.market_contract_metadata,
        contract_mismatch="CONTRACT_CONFLICT" in blockers,
        rollover_active=any(item.rollover_active for item in evidence_set),
        near_price_limit=any(item.near_price_limit for item in evidence_set),
        stop_distance_ratio=stop_distance_ratio,
        max_stop_distance_ratio=float(
            risk_values.get("max_stop_distance_ratio", 0.03)
        ),
        account_risk_limit=(
            float(account_risk_limit)
            if isinstance(account_risk_limit, (int, float))
            else None
        ),
        proposed_risk=(
            float(proposed_risk)
            if isinstance(proposed_risk, (int, float))
            else None
        ),
        correlated_exposure_exceeded=correlated_exposure_exceeded,
        forced_exit=forced_exit,
        position_invalidated=position_invalidated,
        reduce_required=reduce_required,
        add_confirmation=add_confirmation,
    )
