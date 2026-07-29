import json
from datetime import datetime, timezone

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_sqlite_upgrade_from_0001_backfills_analysis_sequence(tmp_path) -> None:
    database_path = tmp_path / "legacy.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "0001")

    created_at = datetime(2026, 7, 20, tzinfo=timezone.utc).isoformat()
    analysis_payload = {
        "analysis_id": "analysis-legacy",
        "decision": {"action": "HOLD"},
    }
    case_state = {
        "case_id": "case-legacy",
        "analysis_ids": ["analysis-legacy"],
    }
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO cases(case_id, state, created_at) "
                "VALUES (:case_id, :state, :created_at)"
            ),
            {
                "case_id": "case-legacy",
                "state": json.dumps(case_state),
                "created_at": created_at,
            },
        )
        connection.execute(
            text(
                "INSERT INTO case_events("
                "event_id, case_id, event_type, payload, created_at"
                ") VALUES ("
                ":event_id, :case_id, :event_type, :payload, :created_at"
                ")"
            ),
            {
                "event_id": "event-analysis",
                "case_id": "case-legacy",
                "event_type": "ANALYSIS_COMPLETED",
                "payload": json.dumps(analysis_payload),
                "created_at": created_at,
            },
        )
        connection.execute(
            text(
                "INSERT INTO analyses(analysis_id, case_id, payload) "
                "VALUES (:analysis_id, :case_id, :payload)"
            ),
            {
                "analysis_id": "analysis-legacy",
                "case_id": "case-legacy",
                "payload": json.dumps(analysis_payload),
            },
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        sequence = connection.execute(
            text(
                "SELECT sequence FROM analyses "
                "WHERE analysis_id = 'analysis-legacy'"
            )
        ).scalar_one()
    assert sequence == 1


def test_authentication_migration_creates_users_and_sessions(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'auth.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)

    command.upgrade(config, "head")

    inspector = inspect(create_engine(database_url))
    assert {"users", "auth_sessions"}.issubset(inspector.get_table_names())
    assert {
        "user_id",
        "username",
        "password_hash",
        "is_active",
        "created_at",
        "updated_at",
    } == {column["name"] for column in inspector.get_columns("users")}
    assert {
        "session_id",
        "user_id",
        "token_hash",
        "created_at",
        "expires_at",
    } == {column["name"] for column in inspector.get_columns("auth_sessions")}
