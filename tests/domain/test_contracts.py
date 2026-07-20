import pytest
from pydantic import ValidationError

from trading_agent.domain.decision import ActionDecision
from trading_agent.domain.enums import (
    ActionType,
    MarketState,
    MilestoneStatus,
)
from trading_agent.domain.evidence import Evidence
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.domain.milestone import StrategyEvaluation


def test_decision_requires_blocking_steps_when_waiting_for_data() -> None:
    with pytest.raises(ValidationError):
        ActionDecision(
            action=ActionType.WAIT_FOR_DATA,
            market_state=MarketState.U,
            supporting_steps=[],
            blocking_steps=[],
            reason_codes=["CONTRACT_MISSING"],
            evidence_refs=[],
        )


def test_evidence_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        Evidence(
            evidence_id="evidence-1",
            kind="TIMEFRAME",
            value="1d",
            confidence=1.1,
            provenance="codex:gpt-5.6-sol",
        )


def test_milestone_exposes_rules_blockers_and_next_conditions() -> None:
    milestone = MilestoneResult(
        number=1,
        code="DATA_VALIDITY",
        status=MilestoneStatus.BLOCKED,
        result="PARTIAL",
        rule_ids=["DQ-CONTRACT-001"],
        evidence_refs=["evidence-1"],
        blockers=["CONTRACT_MISSING"],
        next_conditions=["Provide the real contract"],
    )

    assert milestone.number == 1
    assert milestone.blockers == ["CONTRACT_MISSING"]


def test_strategy_evaluation_requires_exactly_eight_unique_steps() -> None:
    step = MilestoneResult(
        number=1,
        code="DATA_VALIDITY",
        status=MilestoneStatus.CONFIRMED,
        result="VALID",
    )

    with pytest.raises(ValidationError):
        StrategyEvaluation(steps=[step])


@pytest.mark.parametrize(
    ("supporting_steps", "blocking_steps"),
    [
        ([0], []),
        ([9], []),
        ([1, 1], []),
        ([1], [1]),
    ],
)
def test_decision_rejects_invalid_milestone_references(
    supporting_steps: list[int],
    blocking_steps: list[int],
) -> None:
    with pytest.raises(ValidationError):
        ActionDecision(
            action=ActionType.WAIT_FOR_SETUP,
            market_state=MarketState.U,
            supporting_steps=supporting_steps,
            blocking_steps=blocking_steps,
        )


def test_entry_requires_strategy_confirmation_and_no_blockers() -> None:
    with pytest.raises(ValidationError):
        ActionDecision(
            action=ActionType.ENTER_CONDITIONAL,
            market_state=MarketState.U,
            supporting_steps=[2],
            blocking_steps=[1],
        )
