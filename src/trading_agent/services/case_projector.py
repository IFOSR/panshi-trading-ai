from trading_agent.domain.case import CaseState, PositionState
from trading_agent.domain.events import (
    AnalysisIssued,
    CaseCreated,
    ImageUploaded,
    PositionUpdated,
    TradingCaseEvent,
)


def replay_case(events: list[TradingCaseEvent]) -> CaseState:
    state: CaseState | None = None

    for event in events:
        if isinstance(event, CaseCreated):
            if state is None:
                state = CaseState(
                    case_id=event.case_id,
                    instrument=event.instrument,
                    contract=event.contract,
                )
                continue
            if event.contract != state.contract or event.instrument != state.instrument:
                raise ValueError("instrument or contract cannot change inside an existing case")
            continue

        if state is None:
            raise ValueError("CASE_CREATED must be the first event")
        if event.case_id != state.case_id:
            raise ValueError("event case_id does not match the replayed case")

        if isinstance(event, PositionUpdated):
            state.position = PositionState(
                direction=event.direction,
                quantity=event.quantity,
                average_cost=event.average_cost,
                stop_price=event.stop_price,
            )
        elif isinstance(event, ImageUploaded):
            state.image_ids.append(event.image_id)
        elif isinstance(event, AnalysisIssued):
            state.analysis_ids.append(event.analysis_id)

    if state is None:
        raise ValueError("at least one CASE_CREATED event is required")
    return state
