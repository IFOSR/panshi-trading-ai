from datetime import datetime, timedelta, timezone
from threading import Barrier, Lock, Thread

import pytest
from sqlalchemy import event
from sqlalchemy.dialects import postgresql

from trading_agent.db.base import Base, build_engine, session_factory
from trading_agent.db.models import (
    AnalysisRecord,
    CaseEventRecord,
    CaseRecord,
    IdempotencyRecord,
)
from trading_agent.db.repositories import (
    CaseRepository,
    CaseVersionConflict,
    CommandInProgress,
    build_event_sequence_allocation_statement,
    build_idempotency_takeover_statement,
)


def make_sessions():
    engine = build_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return session_factory(engine)


def test_case_state_is_rebuilt_from_ordered_events_not_mutable_snapshot() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            state = repo.create_case("rb", "rb2610")
            case_id = state["case_id"]
            state["position"] = {"direction": "LONG", "quantity": 2}
            repo.update_case(case_id, state, "POSITION_UPDATED", state["position"])
            session.get(CaseRecord, case_id).state = {"corrupted": True}

    with sessions() as session:
        repo = CaseRepository(session)
        rebuilt = repo.get_case(case_id)
        events = (
            session.query(CaseEventRecord)
            .filter(CaseEventRecord.case_id == case_id)
            .order_by(CaseEventRecord.sequence)
            .all()
        )

    assert rebuilt["position"] == {"direction": "LONG", "quantity": 2}
    assert [event.sequence for event in events] == [1, 2]


def test_idempotency_key_has_single_owner_until_completed() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            case_id = repo.create_case(None, None)["case_id"]

    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            assert repo.claim_idempotency(case_id, "analysis", "same-key", "owner-1") is None

    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            with pytest.raises(CommandInProgress):
                repo.claim_idempotency(case_id, "analysis", "same-key", "owner-2")

    with sessions() as session:
        with session.begin():
            CaseRepository(session).complete_idempotency(
                case_id,
                "analysis",
                "same-key",
                "owner-1",
                {"analysis_id": "analysis-1"},
            )

    with sessions() as session:
        with session.begin():
            cached = CaseRepository(session).claim_idempotency(
                case_id,
                "analysis",
                "same-key",
                "owner-2",
            )

    assert cached == {"analysis_id": "analysis-1"}


def test_failed_idempotency_claim_can_be_owned_by_a_retry() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            case_id = repo.create_case(None, None)["case_id"]
            repo.claim_idempotency(case_id, "analysis", "same-key", "owner-1")
            repo.fail_idempotency(case_id, "analysis", "same-key", "owner-1")

    with sessions() as session:
        with session.begin():
            claimed = CaseRepository(session).claim_idempotency(
                case_id,
                "analysis",
                "same-key",
                "owner-2",
            )

    assert claimed is None


def test_expired_pending_idempotency_claim_can_be_owned_after_cancellation() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            case_id = repo.create_case(None, None)["case_id"]
            repo.claim_idempotency(case_id, "analysis", "same-key", "owner-1")
            record = session.query(IdempotencyRecord).filter_by(
                case_id=case_id,
                command="analysis",
                key="same-key",
            ).one()
            record.claimed_at = datetime(2020, 1, 1, tzinfo=timezone.utc)

    with sessions() as session:
        with session.begin():
            claimed = CaseRepository(session).claim_idempotency(
                case_id,
                "analysis",
                "same-key",
                "owner-2",
            )

    assert claimed is None


def test_idempotency_takeover_is_one_conditional_database_update() -> None:
    statement = build_idempotency_takeover_statement(
        case_id="case-1",
        command="analysis",
        key="same-key",
        owner_id="owner-2",
        now=datetime(2026, 7, 20, tzinfo=timezone.utc),
        lease=timedelta(minutes=5),
    )

    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert compiled.startswith("UPDATE idempotency_keys SET")
    assert "idempotency_keys.status = 'FAILED'" in compiled
    assert "idempotency_keys.status = 'PENDING'" in compiled
    assert "idempotency_keys.claimed_at <=" in compiled
    assert "idempotency_keys.owner_id != 'owner-2'" in compiled


def test_event_sequence_allocation_is_one_postgresql_update_returning() -> None:
    statement = build_event_sequence_allocation_statement(case_id="case-1")

    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert compiled.startswith("UPDATE cases SET version=(cases.version + 1)")
    assert "WHERE cases.case_id = 'case-1'" in compiled
    assert compiled.endswith("RETURNING cases.version")


def test_expected_case_version_is_claimed_by_the_sequence_update() -> None:
    statement = build_event_sequence_allocation_statement(
        case_id="case-1",
        expected_version=7,
    )

    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "cases.version = 7" in compiled
    assert compiled.endswith("RETURNING cases.version")


def test_only_first_retry_can_take_over_an_expired_claim() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            case_id = repo.create_case(None, None)["case_id"]
            repo.claim_idempotency(case_id, "analysis", "same-key", "owner-1")
            record = session.query(IdempotencyRecord).filter_by(
                case_id=case_id,
                command="analysis",
                key="same-key",
            ).one()
            record.claimed_at = datetime(2020, 1, 1, tzinfo=timezone.utc)

    with sessions() as session:
        with session.begin():
            assert (
                CaseRepository(session).claim_idempotency(
                    case_id,
                    "analysis",
                    "same-key",
                    "owner-2",
                )
                is None
            )

    with sessions() as session:
        with session.begin():
            with pytest.raises(CommandInProgress):
                CaseRepository(session).claim_idempotency(
                    case_id,
                    "analysis",
                    "same-key",
                    "owner-3",
                )


def test_current_owner_can_atomically_renew_its_idempotency_lease() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            case_id = repo.create_case(None, None)["case_id"]
            repo.claim_idempotency(case_id, "analysis", "same-key", "owner-1")
            record = session.query(IdempotencyRecord).filter_by(
                case_id=case_id,
                command="analysis",
                key="same-key",
            ).one()
            record.claimed_at = datetime(2020, 1, 1, tzinfo=timezone.utc)

    with sessions() as session:
        with session.begin():
            renewed = CaseRepository(session).renew_idempotency(
                case_id,
                "analysis",
                "same-key",
                "owner-1",
            )

    assert renewed is True
    with sessions() as session:
        with session.begin():
            with pytest.raises(CommandInProgress):
                CaseRepository(session).claim_idempotency(
                    case_id,
                    "analysis",
                    "same-key",
                    "owner-2",
                )


def test_non_owner_cannot_renew_an_idempotency_lease() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            case_id = repo.create_case(None, None)["case_id"]
            repo.claim_idempotency(case_id, "analysis", "same-key", "owner-1")

    with sessions() as session:
        with session.begin():
            renewed = CaseRepository(session).renew_idempotency(
                case_id,
                "analysis",
                "same-key",
                "owner-2",
            )

    assert renewed is False


def test_completed_idempotency_result_cannot_be_overwritten_by_late_owner() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            case_id = repo.create_case(None, None)["case_id"]
            repo.claim_idempotency(case_id, "analysis", "same-key", "owner-1")
            repo.complete_idempotency(
                case_id,
                "analysis",
                "same-key",
                "owner-1",
                {"analysis_id": "winner"},
            )

    with sessions() as session:
        with session.begin():
            with pytest.raises(CommandInProgress):
                CaseRepository(session).complete_idempotency(
                    case_id,
                    "analysis",
                    "same-key",
                    "owner-2",
                    {"analysis_id": "late"},
                )

    with sessions() as session:
        assert CaseRepository(session).idempotent_result(
            case_id,
            "analysis",
            "same-key",
        ) == {"analysis_id": "winner"}


def test_analysis_persistence_rejects_stale_case_version() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            state = repo.create_case(None, None)
            case_id = state["case_id"]
            loaded_version = repo.case_version(case_id)
            state["position"] = {"direction": "LONG", "quantity": 1}
            repo.update_case(case_id, state, "POSITION_UPDATED", state["position"])

    with sessions() as session:
        with session.begin():
            with pytest.raises(CaseVersionConflict):
                CaseRepository(session).save_analysis(
                    case_id,
                    {"analysis_id": "stale", "decision": {"action": "HOLD"}},
                    expected_case_version=loaded_version,
                )


def test_analyses_are_returned_in_insertion_order_not_uuid_order() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            case_id = repo.create_case(None, None)["case_id"]
            repo.save_analysis(
                case_id,
                {"analysis_id": "z-analysis", "decision": {"action": "WAIT_FOR_DATA"}},
            )
            repo.save_analysis(
                case_id,
                {"analysis_id": "a-analysis", "decision": {"action": "WAIT_FOR_SETUP"}},
            )

    with sessions() as session:
        analyses = CaseRepository(session).analyses(case_id)

    assert [item["analysis_id"] for item in analyses] == ["z-analysis", "a-analysis"]


def test_clarification_proposals_are_rebuilt_in_event_order() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            state = repo.create_case("CF", "CF2609")
            case_id = state["case_id"]
            repo.append_event(
                case_id,
                "CLARIFICATION_PROPOSED",
                {
                    "clarification_id": "clarification-1",
                    "source_analysis_id": "analysis-1",
                    "user_message": "日线已收盘",
                    "facts": [],
                    "unresolved_question_ids": ["execution-bar"],
                    "interpretation": "日线最后一根 K 线已收盘。",
                    "provider": "codex",
                    "model": "gpt-5.6-sol",
                    "status": "PENDING_CONFIRMATION",
                },
            )
            repo.append_event(
                case_id,
                "CLARIFICATION_PROPOSED",
                {
                    "clarification_id": "clarification-2",
                    "source_analysis_id": "analysis-1",
                    "user_message": "60 分钟也已收盘",
                    "facts": [],
                    "unresolved_question_ids": [],
                    "interpretation": "60 分钟最后一根 K 线已收盘。",
                    "provider": "codex",
                    "model": "gpt-5.6-sol",
                    "status": "PENDING_CONFIRMATION",
                },
            )
            session.get(CaseRecord, case_id).state = {"corrupted": True}

    with sessions() as session:
        rebuilt = CaseRepository(session).get_case(case_id)

    assert [item["clarification_id"] for item in rebuilt["clarifications"]] == [
        "clarification-1",
        "clarification-2",
    ]
    assert rebuilt["clarifications"][0]["status"] == "PENDING_CONFIRMATION"


def test_clarification_confirmation_updates_history_without_losing_case_history() -> None:
    sessions = make_sessions()
    fact = {
        "question_id": "daily-close",
        "field": "state_bar_closed",
        "value": True,
        "explanation": "用户确认日线最后一根 K 线已经收盘。",
        "resolves_blockers": ["STATE_BAR_NOT_CLOSED"],
    }
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            state = repo.create_case("CF", "CF2609")
            case_id = state["case_id"]
            repo.save_analysis(
                case_id,
                {"analysis_id": "analysis-1", "decision": {"action": "WAIT_FOR_DATA"}},
            )
            repo.append_event(
                case_id,
                "USER_ACTION_RECORDED",
                {"action": "ACKNOWLEDGE", "analysis_id": "analysis-1"},
            )
            repo.append_event(
                case_id,
                "CLARIFICATION_PROPOSED",
                {
                    "clarification_id": "clarification-1",
                    "source_analysis_id": "analysis-1",
                    "user_message": "日线已收盘",
                    "facts": [fact],
                    "unresolved_question_ids": [],
                    "interpretation": "日线最后一根 K 线已收盘。",
                    "provider": "codex",
                    "model": "gpt-5.6-sol",
                    "status": "PENDING_CONFIRMATION",
                },
            )
            repo.append_event(
                case_id,
                "CLARIFICATION_CONFIRMED",
                {
                    "clarification_id": "clarification-1",
                    "confirmed_at": "2026-07-22T08:30:00Z",
                    "result_analysis_id": "analysis-2",
                },
            )
            session.get(CaseRecord, case_id).state = {"corrupted": True}

    with sessions() as session:
        rebuilt = CaseRepository(session).get_case(case_id)

    clarification = rebuilt["clarifications"][0]
    assert clarification["status"] == "CONFIRMED"
    assert clarification["confirmed_at"] == "2026-07-22T08:30:00Z"
    assert clarification["result_analysis_id"] == "analysis-2"
    assert rebuilt["confirmed_clarification_facts"] == [
        {
            **fact,
            "clarification_id": "clarification-1",
            "confirmed_at": "2026-07-22T08:30:00Z",
        }
    ]
    assert rebuilt["analysis_ids"] == ["analysis-1"]
    assert rebuilt["action_history"] == [
        {"action": "ACKNOWLEDGE", "analysis_id": "analysis-1"}
    ]


def test_different_idempotency_keys_concurrently_allocate_unique_event_sequences(
    tmp_path,
) -> None:
    engine = build_engine(f"sqlite+pysqlite:///{tmp_path / 'concurrent-events.db'}")
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            state = repo.create_case(None, None)
            case_id = state["case_id"]
    for key in ("key-a", "key-b"):
        with sessions() as session:
            with session.begin():
                CaseRepository(session).claim_idempotency(
                    case_id,
                    "action",
                    key,
                    f"owner-{key}",
                )

    stale_read_barrier = Barrier(2)

    @event.listens_for(engine, "before_cursor_execute")
    def synchronize_non_atomic_case_reads(
        connection,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        normalized = " ".join(statement.lower().split())
        if normalized.startswith("update cases set version"):
            connection.info["atomic_sequence_update_seen"] = True
        if (
            "from cases" in normalized
            and "where cases.case_id" in normalized
            and not connection.info.get("atomic_sequence_update_seen")
        ):
            stale_read_barrier.wait(timeout=5)

    errors: list[BaseException] = []
    error_lock = Lock()

    def update_with_key(key: str) -> None:
        try:
            with sessions() as session:
                with session.begin():
                    repo = CaseRepository(session)
                    payload = {"key": key}
                    repo.update_case(
                        case_id,
                        state,
                        "USER_ACTION_RECORDED",
                        payload,
                    )
                    repo.complete_idempotency(
                        case_id,
                        "action",
                        key,
                        f"owner-{key}",
                        payload,
                    )
        except BaseException as exc:
            with error_lock:
                errors.append(exc)

    workers = [
        Thread(target=update_with_key, args=(key,))
        for key in ("key-a", "key-b")
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert all(not worker.is_alive() for worker in workers)
    assert errors == []
    with sessions() as session:
        events = session.query(CaseEventRecord).filter_by(case_id=case_id).all()
        completed = session.query(IdempotencyRecord).filter_by(
            case_id=case_id,
            command="action",
            status="COMPLETED",
        ).all()

    assert sorted(event.sequence for event in events) == [1, 2, 3]
    assert len({event.sequence for event in events}) == 3
    assert {record.key for record in completed} == {"key-a", "key-b"}


def test_delete_case_removes_all_related_records_without_touching_other_cases() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            deleted_case_id = repo.create_case("CF", "CF2609")["case_id"]
            retained_case_id = repo.create_case("RB", "RB2610")["case_id"]
            repo.save_analysis(
                deleted_case_id,
                {"analysis_id": "analysis-delete", "decision": {"action": "EXIT"}},
            )
            repo.save_analysis(
                retained_case_id,
                {"analysis_id": "analysis-retain", "decision": {"action": "HOLD"}},
            )
            repo.claim_idempotency(
                deleted_case_id,
                "analysis",
                "delete-key",
                "delete-owner",
            )
            assert repo.delete_case(deleted_case_id) is True
            assert repo.delete_case(deleted_case_id) is False

    with sessions() as session:
        assert session.get(CaseRecord, deleted_case_id) is None
        assert session.get(CaseRecord, retained_case_id) is not None
        assert session.query(CaseEventRecord).filter_by(
            case_id=deleted_case_id
        ).count() == 0
        assert session.query(AnalysisRecord).filter_by(
            case_id=deleted_case_id
        ).count() == 0
        assert session.query(IdempotencyRecord).filter_by(
            case_id=deleted_case_id
        ).count() == 0
        assert session.query(CaseEventRecord).filter_by(
            case_id=retained_case_id
        ).count() > 0
        assert session.query(AnalysisRecord).filter_by(
            case_id=retained_case_id
        ).count() == 1


def test_delete_all_cases_removes_every_case_and_related_record() -> None:
    sessions = make_sessions()
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            first_id = repo.create_case("CF", "CF2609")["case_id"]
            second_id = repo.create_case("RB", "RB2610")["case_id"]
            repo.save_analysis(
                first_id,
                {"analysis_id": "analysis-first", "decision": {"action": "EXIT"}},
            )
            repo.claim_idempotency(
                second_id,
                "analysis",
                "second-key",
                "second-owner",
            )
            assert repo.delete_all_cases() == 2
            assert repo.delete_all_cases() == 0

    with sessions() as session:
        assert session.query(CaseRecord).count() == 0
        assert session.query(CaseEventRecord).count() == 0
        assert session.query(AnalysisRecord).count() == 0
        assert session.query(IdempotencyRecord).count() == 0
