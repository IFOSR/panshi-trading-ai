import math

import pytest
from pydantic import TypeAdapter, ValidationError

from trading_agent.domain.decision import ActionDecision
from trading_agent.domain.enums import ActionType, MarketState, PositionDirection
from trading_agent.domain.events import (
    AnalysisIssued,
    CaseClosed,
    CaseCreated,
    CaseReviewed,
    ContractResolved,
    ImageParsed,
    MarketStateChanged,
    PositionUpdated,
    SignalAdvanced,
    TradingCaseEvent,
    UserActionReported,
)
from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.services.case_projector import replay_case


def test_case_replay_restores_current_position() -> None:
    state = replay_case(
        [
            CaseCreated(case_id="case-1", instrument="rb", contract="rb2610"),
            PositionUpdated(
                case_id="case-1",
                direction=PositionDirection.LONG,
                quantity=2,
                average_cost=3295,
            ),
        ]
    )

    assert state.position.direction == PositionDirection.LONG
    assert state.position.quantity == 2
    assert state.position.average_cost == 3295


def test_case_replay_rejects_contract_change_inside_same_case() -> None:
    with pytest.raises(ValueError, match="contract"):
        replay_case(
            [
                CaseCreated(case_id="case-1", instrument="rb", contract="rb2610"),
                CaseCreated(case_id="case-1", instrument="rb", contract="rb2701"),
            ]
        )


def test_case_replay_rejects_second_case_created_even_with_same_contract() -> None:
    with pytest.raises(ValueError, match="CASE_CREATED"):
        replay_case(
            [
                CaseCreated(case_id="case-1", instrument="rb", contract="rb2610"),
                CaseCreated(case_id="case-2", instrument="rb", contract="rb2610"),
            ]
        )


def test_position_update_rejects_negative_quantity() -> None:
    with pytest.raises(ValueError):
        PositionUpdated(
            case_id="case-1",
            direction=PositionDirection.LONG,
            quantity=-1,
            average_cost=3295,
        )


def test_position_update_rejects_boolean_quantity_and_non_finite_prices() -> None:
    with pytest.raises(ValidationError):
        PositionUpdated(
            case_id="case-1",
            direction=PositionDirection.LONG,
            quantity=True,
            average_cost=3295,
        )

    with pytest.raises(ValidationError):
        PositionUpdated(
            case_id="case-1",
            direction=PositionDirection.LONG,
            quantity=1,
            average_cost=math.nan,
        )


def test_events_are_immutable() -> None:
    event = CaseCreated(case_id="case-1", instrument="rb", contract="rb2610")

    with pytest.raises(ValidationError):
        event.contract = "rb2701"


def test_case_can_resolve_initially_unknown_contract_once() -> None:
    state = replay_case(
        [
            CaseCreated(case_id="case-1"),
            ContractResolved(case_id="case-1", instrument="rb", contract="rb2610"),
        ]
    )

    assert state.instrument == "rb"
    assert state.contract == "rb2610"

    with pytest.raises(ValueError, match="already resolved"):
        replay_case(
            [
                CaseCreated(case_id="case-1"),
                ContractResolved(case_id="case-1", instrument="rb", contract="rb2610"),
                ContractResolved(case_id="case-1", instrument="rb", contract="rb2701"),
            ]
        )


def test_image_and_advice_events_require_typed_payloads() -> None:
    with pytest.raises(ValidationError):
        ImageParsed(case_id="case-1", image_id="image-1", evidence={"contract": "rb2610"})

    with pytest.raises(ValidationError):
        AnalysisIssued(
            case_id="case-1",
            analysis_id="analysis-1",
            decision={"action": "BUY_NOW"},
        )


def test_event_serialization_round_trip_uses_discriminator() -> None:
    adapter = TypeAdapter(TradingCaseEvent)
    event = PositionUpdated(
        case_id="case-1",
        direction=PositionDirection.SHORT,
        quantity=1,
        average_cost=17000,
    )

    restored = adapter.validate_json(adapter.dump_json(event))

    assert isinstance(restored, PositionUpdated)
    assert restored.direction == PositionDirection.SHORT


def test_replay_restores_strategy_lifecycle_and_current_decision() -> None:
    evidence = ScreenshotEvidence(
        image_role="STATE_DAILY",
        provider="codex",
        model="gpt-5.6-sol",
        prompt_version="chart-evidence-v1",
        image_sha256="abc",
    )
    decision = ActionDecision(
        action=ActionType.WAIT_FOR_DATA,
        market_state=MarketState.U,
        blocking_steps=[1],
        reason_codes=["CONTRACT_MISSING"],
    )
    state = replay_case(
        [
            CaseCreated(case_id="case-1"),
            ImageParsed(case_id="case-1", image_id="image-1", evidence=evidence),
            MarketStateChanged(case_id="case-1", market_state=MarketState.U),
            SignalAdvanced(case_id="case-1", signal_stage="NO_VALID_SETUP"),
            AnalysisIssued(
                case_id="case-1",
                analysis_id="analysis-1",
                decision=decision,
            ),
            UserActionReported(case_id="case-1", action="NO_ACTION"),
            CaseClosed(case_id="case-1", reason="USER_CLOSED"),
            CaseReviewed(case_id="case-1", review_summary="Rules followed"),
        ]
    )

    assert state.current_market_state == MarketState.U
    assert state.signal_stage == "NO_VALID_SETUP"
    assert state.current_decision == decision
    assert state.lifecycle == "REVIEWED"
    assert state.action_history == ["NO_ACTION"]
