from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from trading_agent.db.models import AnalysisRecord, CaseEventRecord, CaseRecord, IdempotencyRecord


class CaseRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_case(self, instrument: str | None, contract: str | None) -> dict:
        case_id = str(uuid4())
        state: dict = {
            "case_id": case_id, "instrument": instrument, "contract": contract,
            "position": {"direction": "FLAT", "quantity": 0},
            "lifecycle": "OBSERVING", "image_ids": [],
        }
        self.session.add(CaseRecord(case_id=case_id, state=state))
        self.append_event(case_id, "CASE_CREATED", {"instrument": instrument, "contract": contract})
        self.session.flush()
        return state

    def get_case(self, case_id: str) -> dict | None:
        record = self.session.get(CaseRecord, case_id)
        return dict(record.state) if record else None

    def update_case(self, case_id: str, state: dict, event_type: str, payload: dict) -> None:
        record = self.session.get(CaseRecord, case_id)
        if record is None:
            raise KeyError(case_id)
        record.state = state
        self.append_event(case_id, event_type, payload)
        self.session.flush()

    def append_event(self, case_id: str, event_type: str, payload: dict) -> None:
        self.session.add(CaseEventRecord(
            event_id=str(uuid4()), case_id=case_id, event_type=event_type, payload=payload
        ))

    def idempotent_result(self, case_id: str, command: str, key: str) -> dict | None:
        record = self.session.scalar(select(IdempotencyRecord).where(
            IdempotencyRecord.case_id == case_id,
            IdempotencyRecord.command == command,
            IdempotencyRecord.key == key,
        ))
        return dict(record.result) if record else None

    def save_idempotent(self, case_id: str, command: str, key: str, result: dict) -> None:
        self.session.add(IdempotencyRecord(
            id=str(uuid4()), case_id=case_id, command=command, key=key, result=result
        ))
        self.session.flush()

    def save_analysis(self, case_id: str, payload: dict) -> None:
        self.session.add(AnalysisRecord(
            analysis_id=payload["analysis_id"], case_id=case_id, payload=payload
        ))
        self.append_event(case_id, "ANALYSIS_COMPLETED", payload)
        self.session.flush()

    def analyses(self, case_id: str) -> list[dict]:
        records = self.session.scalars(
            select(AnalysisRecord).where(AnalysisRecord.case_id == case_id)
        )
        return [dict(record.payload) for record in records]

    def analysis(self, case_id: str, analysis_id: str) -> dict | None:
        record = self.session.get(AnalysisRecord, analysis_id)
        if record is None or record.case_id != case_id:
            return None
        return dict(record.payload)
