from datetime import datetime
from zoneinfo import ZoneInfo

from trading_agent.clarification.evidence import apply_confirmed_facts
from trading_agent.clarification.models import ClarificationFact
from trading_agent.domain.enums import EvidenceUsage, PositionDirection
from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.strategy.context_builder import build_strategy_context


def evidence(
    *,
    role: str,
    timeframe: str,
    last_bar_closed: bool | None = None,
    blockers: list[str] | None = None,
) -> ScreenshotEvidence:
    return ScreenshotEvidence(
        image_role=role,
        contract="CF2609",
        timeframe=timeframe,
        cutoff_time=(
            "2026-07-22T15:00:00+08:00"
            if timeframe == "1d"
            else "2026-07-22T14:00:00+08:00"
        ),
        last_bar_closed=last_bar_closed,
        blocking_issues=blockers or [],
        allowed_usage=EvidenceUsage.QUALITATIVE_ONLY,
        provider="codex",
        model="gpt-5.6-sol",
        prompt_version="chart-evidence-v2",
        image_sha256=f"hash-{role}",
    )


def fact(
    field: str,
    value: bool | float | str,
    *blockers: str,
) -> ClarificationFact:
    return ClarificationFact(
        question_id=f"question-{field}",
        field=field,
        value=value,
        explanation="用户明确确认。",
        resolves_blockers=list(blockers),
    )


def test_user_confirmation_fills_unknown_fields_and_adds_auditable_evidence() -> None:
    merged = apply_confirmed_facts(
        [
            evidence(
                role="STATE_DAILY",
                timeframe="1d",
                blockers=["BAR_CLOSE_UNKNOWN", "OPEN_INTEREST_MISSING"],
            ),
            evidence(
                role="EXECUTION_60M",
                timeframe="60m",
                blockers=["执行周期收盘状态未知。"],
            ),
        ],
        [
            fact("state_bar_closed", True, "BAR_CLOSE_UNKNOWN"),
            fact("execution_bar_closed", True, "执行周期收盘状态未知。"),
            fact("open_interest_change", -4425, "OPEN_INTEREST_MISSING"),
            fact(
                "position_behavior_state",
                "POSITION_LIQUIDATION",
                "CCYD无法确认。",
            ),
            fact("price_confirmation", True, "PRICE_NOT_CONFIRMED"),
            fact("price_confirmation_direction", "BEARISH"),
            fact("price_confirmation_type", "PULLBACK"),
        ],
        clarification_id="clarification-1",
    )

    daily, execution = merged
    assert daily.last_bar_closed is True
    assert daily.open_interest_change == -4425
    assert daily.strategy_facts.position_behavior == "POSITION_LIQUIDATION"
    assert execution.last_bar_closed is True
    assert execution.strategy_facts.price_confirmation is True
    assert execution.strategy_facts.price_confirmation_direction == "BEARISH"
    assert execution.strategy_facts.price_confirmation_type == "PULLBACK"
    assert "BAR_CLOSE_UNKNOWN" not in daily.blocking_issues
    assert "OPEN_INTEREST_MISSING" not in daily.blocking_issues
    assert all(
        observation.provenance == "user_confirmed"
        for item in merged
        for observation in item.observations
    )
    assert all(
        "clarification-1" in observation.evidence_id
        for item in merged
        for observation in item.observations
    )

    context = build_strategy_context(
        merged,
        case_contract="cf2609",
        position=PositionDirection.FLAT,
        analysis_time=datetime(
            2026, 7, 22, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")
        ),
    )
    assert context.state_bar_closed is True
    assert context.open_interest_change == -4425
    assert context.position_behavior_state == "POSITION_LIQUIDATION"
    assert context.price_confirmation is True
    assert context.price_confirmation_direction == "BEARISH"
    assert context.price_confirmation_type == "PULLBACK"


def test_user_confirmation_cannot_overwrite_clear_conflicting_evidence() -> None:
    original = evidence(
        role="STATE_DAILY",
        timeframe="1d",
        last_bar_closed=False,
    )

    merged = apply_confirmed_facts(
        [original],
        [fact("state_bar_closed", True, "UNCLOSED_STATE_BAR")],
        clarification_id="clarification-2",
    )

    assert merged[0].last_bar_closed is False
    assert "USER_CLARIFICATION_CONFLICT" in merged[0].blocking_issues
    assert merged[0].allowed_usage == EvidenceUsage.BLOCKED
