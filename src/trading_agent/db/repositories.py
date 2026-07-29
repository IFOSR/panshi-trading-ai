from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import and_, delete, desc, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from trading_agent.db.models import AnalysisRecord, CaseEventRecord, CaseRecord, IdempotencyRecord


class CommandInProgress(RuntimeError):
    pass


class CaseVersionConflict(RuntimeError):
    pass


def build_event_sequence_allocation_statement(
    *,
    case_id: str,
    expected_version: int | None = None,
):
    statement = (
        update(CaseRecord)
        .where(CaseRecord.case_id == case_id)
        .values(version=CaseRecord.version + 1)
        .returning(CaseRecord.version)
    )
    if expected_version is not None:
        statement = statement.where(CaseRecord.version == expected_version)
    return statement


def build_idempotency_takeover_statement(
    *,
    case_id: str,
    command: str,
    key: str,
    owner_id: str,
    now: datetime,
    lease: timedelta,
):
    return (
        update(IdempotencyRecord)
        .where(
            IdempotencyRecord.case_id == case_id,
            IdempotencyRecord.command == command,
            IdempotencyRecord.key == key,
            IdempotencyRecord.owner_id != owner_id,
            or_(
                IdempotencyRecord.status == "FAILED",
                and_(
                    IdempotencyRecord.status == "PENDING",
                    IdempotencyRecord.claimed_at <= now - lease,
                ),
            ),
        )
        .values(
            status="PENDING",
            owner_id=owner_id,
            claimed_at=now,
            result=None,
        )
    )


class CaseRepository:
    idempotency_lease = timedelta(minutes=10)

    def __init__(self, session: Session) -> None:
        self.session = session

    def create_case(
        self,
        instrument: str | None,
        contract: str | None,
        *,
        case_id: str | None = None,
        creation_request_sha256: str | None = None,
        position: dict | None = None,
        risk: dict | None = None,
        user_input: dict | None = None,
        strategy: dict | None = None,
    ) -> dict:
        resolved_case_id = case_id or str(uuid4())
        state: dict = {
            "case_id": resolved_case_id,
            "instrument": instrument,
            "contract": contract,
            "position": position or {"direction": "UNKNOWN", "quantity": 0},
            "lifecycle": "OBSERVING",
            "image_ids": [],
            "images": [],
            "analysis_ids": [],
            "strategy": strategy or {
                "strategy_id": "structure_confirmation",
                "version": "1.0.0",
                "display_name": "结构确认策略",
            },
            "messages": [],
        }
        if creation_request_sha256:
            state["creation_request_sha256"] = creation_request_sha256
        if risk:
            state["risk"] = risk
        if user_input:
            state["user_input"] = user_input
            raw_message = user_input.get("raw_message")
            if raw_message:
                state["messages"].append(
                    {
                        "message_id": str(uuid4()),
                        "role": "user",
                        "message_type": "USER_MESSAGE",
                        "content": str(raw_message),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "analysis_id": None,
                        "metadata": {},
                    }
                )
        self.session.add(
            CaseRecord(case_id=resolved_case_id, state=state, version=0)
        )
        self.session.flush()
        self.append_event(resolved_case_id, "CASE_CREATED", state)
        return deepcopy(state)

    @staticmethod
    def _apply_event(state: dict, event_type: str, payload: dict) -> dict:
        if event_type == "CASE_CREATED":
            return deepcopy(payload)
        if event_type == "POSITION_UPDATED":
            state["position"] = deepcopy(payload)
        elif event_type == "RISK_UPDATED":
            state["risk"] = deepcopy(payload)
        elif event_type == "IMAGE_UPLOADED":
            state.setdefault("image_ids", []).append(payload["image_id"])
            state.setdefault("images", []).append(deepcopy(payload))
        elif event_type == "ANALYSIS_COMPLETED":
            analysis_id = payload["analysis_id"]
            state.setdefault("analysis_ids", []).append(analysis_id)
            state["current_analysis_id"] = analysis_id
            state["current_decision"] = deepcopy(payload.get("decision"))
            messages = state.setdefault("messages", [])
            message_id = f"analysis:{analysis_id}"
            if not any(item.get("message_id") == message_id for item in messages):
                manifest = payload.get("strategy_manifest", {})
                messages.append(
                    {
                        "message_id": message_id,
                        "role": "assistant",
                        "message_type": "STRATEGY_CONCLUSION",
                        "content": str(
                            payload.get("rendered", {}).get(
                                "summary",
                                payload.get("decision", {}).get("action", "分析完成"),
                            )
                        ),
                        "created_at": str(payload.get("created_at", "")),
                        "analysis_id": analysis_id,
                        "metadata": {
                            "action": payload.get("decision", {}).get("action"),
                            "strategy_id": manifest.get("strategy_id"),
                            "strategy_version": manifest.get("version"),
                        },
                    }
                )
        elif event_type == "CLARIFICATION_PROPOSED":
            state.setdefault("clarifications", []).append(deepcopy(payload))
        elif event_type == "CLARIFICATION_CONFIRMED":
            clarification_id = payload["clarification_id"]
            clarification = next(
                (
                    item
                    for item in state.setdefault("clarifications", [])
                    if item["clarification_id"] == clarification_id
                ),
                None,
            )
            if clarification is not None:
                clarification["status"] = "CONFIRMED"
                clarification["confirmed_at"] = payload["confirmed_at"]
                clarification["result_analysis_id"] = payload["result_analysis_id"]
                confirmed_facts = state.setdefault(
                    "confirmed_clarification_facts",
                    [],
                )
                confirmed_facts.extend(
                    {
                        **deepcopy(fact),
                        "clarification_id": clarification_id,
                        "confirmed_at": payload["confirmed_at"],
                    }
                    for fact in clarification.get("facts", [])
                )
        elif event_type == "USER_ACTION_RECORDED":
            state.setdefault("action_history", []).append(deepcopy(payload))
        elif event_type == "CONVERSATION_MESSAGE_RECORDED":
            state.setdefault("messages", []).append(deepcopy(payload))
        elif event_type == "STRATEGY_SELECTED":
            strategy = payload.get("strategy", payload)
            state["strategy"] = deepcopy(strategy)
            message = payload.get("message")
            if isinstance(message, dict):
                state.setdefault("messages", []).append(deepcopy(message))
        elif event_type == "CASE_CLOSED":
            state["lifecycle"] = "CLOSED"
        return state

    def get_case(self, case_id: str) -> dict | None:
        record = self.session.get(CaseRecord, case_id)
        if record is None:
            return None
        events = self.session.scalars(
            select(CaseEventRecord)
            .where(CaseEventRecord.case_id == case_id)
            .order_by(CaseEventRecord.sequence)
        )
        state: dict = {}
        for event in events:
            state = self._apply_event(state, event.event_type, event.payload)
        return state or deepcopy(record.state)

    def list_cases(self, limit: int | None = 50) -> list[dict]:
        statement = select(CaseRecord).order_by(desc(CaseRecord.created_at))
        if limit is not None:
            statement = statement.limit(limit)
        records = list(self.session.scalars(statement))
        results: list[dict] = []
        for record in records:
            state = self.get_case(record.case_id) or {}
            results.append(
                {
                    "case_id": record.case_id,
                    "contract": state.get("contract"),
                    "instrument": state.get("instrument"),
                    "strategy": deepcopy(state.get("strategy")),
                    "current_decision": deepcopy(state.get("current_decision")),
                    "lifecycle": state.get("lifecycle"),
                    "created_at": record.created_at.isoformat(),
                }
            )
        return results

    def case_ids(self) -> list[str]:
        return list(self.session.scalars(select(CaseRecord.case_id)))

    def delete_case(self, case_id: str) -> bool:
        if self.session.get(CaseRecord, case_id) is None:
            return False
        self.session.execute(
            delete(IdempotencyRecord).where(IdempotencyRecord.case_id == case_id)
        )
        self.session.execute(
            delete(AnalysisRecord).where(AnalysisRecord.case_id == case_id)
        )
        self.session.execute(
            delete(CaseEventRecord).where(CaseEventRecord.case_id == case_id)
        )
        self.session.execute(
            delete(CaseRecord).where(CaseRecord.case_id == case_id)
        )
        self.session.flush()
        return True

    def delete_all_cases(self) -> int:
        case_ids = list(self.session.scalars(select(CaseRecord.case_id)))
        if not case_ids:
            return 0
        self.session.execute(delete(IdempotencyRecord))
        self.session.execute(delete(AnalysisRecord))
        self.session.execute(delete(CaseEventRecord))
        self.session.execute(delete(CaseRecord))
        self.session.flush()
        return len(case_ids)

    def case_version(self, case_id: str) -> int:
        record = self.session.get(CaseRecord, case_id)
        if record is None:
            raise KeyError(case_id)
        return record.version

    def update_case(self, case_id: str, state: dict, event_type: str, payload: dict) -> None:
        record = self.session.get(CaseRecord, case_id)
        if record is None:
            raise KeyError(case_id)
        self.append_event(case_id, event_type, payload)
        record.state = deepcopy(state)
        self.session.flush()

    def append_event(
        self,
        case_id: str,
        event_type: str,
        payload: dict,
        *,
        expected_version: int | None = None,
    ) -> int:
        sequence = self.session.scalar(
            build_event_sequence_allocation_statement(
                case_id=case_id,
                expected_version=expected_version,
            ).execution_options(synchronize_session=False)
        )
        if sequence is None:
            if expected_version is not None:
                current_version = self.session.scalar(
                    select(CaseRecord.version).where(CaseRecord.case_id == case_id)
                )
                if current_version is not None:
                    raise CaseVersionConflict(
                        f"case {case_id} changed from version "
                        f"{expected_version} to {current_version}"
                    )
            raise KeyError(case_id)
        record = self.session.get(CaseRecord, case_id)
        if record is not None:
            self.session.expire(record, ["version"])
        self.session.add(
            CaseEventRecord(
                event_id=str(uuid4()),
                case_id=case_id,
                event_type=event_type,
                payload=deepcopy(payload),
                sequence=sequence,
            )
        )
        self.session.flush()
        return sequence

    def idempotent_result(self, case_id: str, command: str, key: str) -> dict | None:
        record = self.session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.case_id == case_id,
                IdempotencyRecord.command == command,
                IdempotencyRecord.key == key,
                IdempotencyRecord.status == "COMPLETED",
            )
        )
        return deepcopy(record.result) if record and record.result is not None else None

    def claim_idempotency(
        self,
        case_id: str,
        command: str,
        key: str,
        owner_id: str,
    ) -> dict | None:
        now = datetime.now(timezone.utc)
        record = self.session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.case_id == case_id,
                IdempotencyRecord.command == command,
                IdempotencyRecord.key == key,
            )
        )
        if record is None:
            try:
                with self.session.begin_nested():
                    self.session.add(
                        IdempotencyRecord(
                            id=str(uuid4()),
                            case_id=case_id,
                            command=command,
                            key=key,
                            status="PENDING",
                            owner_id=owner_id,
                            claimed_at=now,
                            result=None,
                        )
                    )
                    self.session.flush()
                return None
            except IntegrityError:
                record = self.session.scalar(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.case_id == case_id,
                        IdempotencyRecord.command == command,
                        IdempotencyRecord.key == key,
                    )
                )
        if record is None:
            raise CommandInProgress(f"{command}:{key}")
        if record.status == "COMPLETED" and record.result is not None:
            return deepcopy(record.result)
        if record.owner_id == owner_id:
            return None
        takeover = self.session.execute(
            build_idempotency_takeover_statement(
                case_id=case_id,
                command=command,
                key=key,
                owner_id=owner_id,
                now=now,
                lease=self.idempotency_lease,
            ).execution_options(synchronize_session=False)
        )
        if takeover.rowcount == 1:
            self.session.expire(record)
            return None
        self.session.expire(record)
        self.session.refresh(record)
        if record.status == "COMPLETED" and record.result is not None:
            return deepcopy(record.result)
        raise CommandInProgress(f"{command}:{key}")

    def complete_idempotency(
        self,
        case_id: str,
        command: str,
        key: str,
        owner_id: str,
        result: dict,
    ) -> None:
        record = self.session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.case_id == case_id,
                IdempotencyRecord.command == command,
                IdempotencyRecord.key == key,
            )
        )
        if record is None:
            record = IdempotencyRecord(
                id=str(uuid4()),
                case_id=case_id,
                command=command,
                key=key,
                owner_id=owner_id,
                status="COMPLETED",
                claimed_at=datetime.now(timezone.utc),
                result=deepcopy(result),
            )
            self.session.add(record)
        elif record.owner_id != owner_id:
            raise CommandInProgress(f"{command}:{key}")
        else:
            record.status = "COMPLETED"
            record.result = deepcopy(result)
        self.session.flush()

    def renew_idempotency(
        self,
        case_id: str,
        command: str,
        key: str,
        owner_id: str,
    ) -> bool:
        renewed = self.session.execute(
            update(IdempotencyRecord)
            .where(
                IdempotencyRecord.case_id == case_id,
                IdempotencyRecord.command == command,
                IdempotencyRecord.key == key,
                IdempotencyRecord.owner_id == owner_id,
                IdempotencyRecord.status == "PENDING",
            )
            .values(claimed_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        self.session.flush()
        return renewed.rowcount == 1

    def fail_idempotency(
        self,
        case_id: str,
        command: str,
        key: str,
        owner_id: str,
    ) -> None:
        record = self.session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.case_id == case_id,
                IdempotencyRecord.command == command,
                IdempotencyRecord.key == key,
                IdempotencyRecord.owner_id == owner_id,
            )
        )
        if record is not None and record.status == "PENDING":
            record.status = "FAILED"
            self.session.flush()

    def save_idempotent(self, case_id: str, command: str, key: str, result: dict) -> None:
        self.complete_idempotency(case_id, command, key, "legacy", result)

    def save_analysis(
        self,
        case_id: str,
        payload: dict,
        *,
        expected_case_version: int | None = None,
    ) -> None:
        state = self.get_case(case_id)
        if state is None:
            raise KeyError(case_id)
        analysis_sequence = self.append_event(
            case_id,
            "ANALYSIS_COMPLETED",
            payload,
            expected_version=expected_case_version,
        )
        self.session.add(
            AnalysisRecord(
                analysis_id=payload["analysis_id"],
                case_id=case_id,
                sequence=analysis_sequence,
                payload=deepcopy(payload),
            )
        )
        state = self._apply_event(state, "ANALYSIS_COMPLETED", payload)
        record = self.session.get(CaseRecord, case_id)
        if record is None:
            raise KeyError(case_id)
        record.state = state
        self.session.flush()

    def analyses(self, case_id: str) -> list[dict]:
        records = self.session.scalars(
            select(AnalysisRecord)
            .where(AnalysisRecord.case_id == case_id)
            .order_by(AnalysisRecord.sequence)
        )
        return [deepcopy(record.payload) for record in records]

    def analysis(self, case_id: str, analysis_id: str) -> dict | None:
        record = self.session.get(AnalysisRecord, analysis_id)
        if record is None or record.case_id != case_id:
            return None
        return deepcopy(record.payload)
