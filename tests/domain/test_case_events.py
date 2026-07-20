import pytest

from trading_agent.domain.enums import PositionDirection
from trading_agent.domain.events import CaseCreated, PositionUpdated
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


def test_position_update_rejects_negative_quantity() -> None:
    with pytest.raises(ValueError):
        PositionUpdated(
            case_id="case-1",
            direction=PositionDirection.LONG,
            quantity=-1,
            average_cost=3295,
        )
