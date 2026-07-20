from trading_agent.domain.case import CaseState, PositionState
from trading_agent.domain.events import (
    AnalysisIssued,
    CaseClosed,
    CaseCreated,
    CaseReviewed,
    ContractResolved,
    ImageParsed,
    ImageUploaded,
    MarketStateChanged,
    PositionUpdated,
    SignalAdvanced,
    TradingCaseEvent,
    UserActionReported,
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
            raise ValueError(
                "CASE_CREATED may only appear once; instrument and contract cannot be redefined"
            )

        if state is None:
            raise ValueError("CASE_CREATED must be the first event")
        if event.case_id != state.case_id:
            raise ValueError("event case_id does not match the replayed case")

        if isinstance(event, ContractResolved):
            if state.instrument is not None or state.contract is not None:
                raise ValueError("instrument and contract are already resolved")
            state.instrument = event.instrument
            state.contract = event.contract
        elif isinstance(event, PositionUpdated):
            state.position = PositionState(
                direction=event.direction,
                quantity=event.quantity,
                average_cost=event.average_cost,
                stop_price=event.stop_price,
            )
        elif isinstance(event, ImageUploaded):
            state.image_ids.append(event.image_id)
        elif isinstance(event, ImageParsed):
            state.parsed_images[event.image_id] = event.evidence
        elif isinstance(event, MarketStateChanged):
            state.current_market_state = event.market_state
        elif isinstance(event, SignalAdvanced):
            state.signal_stage = event.signal_stage
        elif isinstance(event, AnalysisIssued):
            state.analysis_ids.append(event.analysis_id)
            state.current_decision = event.decision
        elif isinstance(event, UserActionReported):
            state.action_history.append(event.action)
        elif isinstance(event, CaseClosed):
            state.lifecycle = "CLOSED"
        elif isinstance(event, CaseReviewed):
            state.lifecycle = "REVIEWED"
            state.review_summary = event.review_summary

    if state is None:
        raise ValueError("at least one CASE_CREATED event is required")
    return state
