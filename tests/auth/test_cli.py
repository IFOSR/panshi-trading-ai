from io import StringIO

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select

from trading_agent.auth.cli import main
from trading_agent.auth.passwords import verify_password
from trading_agent.db.models import UserRecord


def migrated_database_url(tmp_path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'auth-cli.db'}"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    return database_url


def test_set_password_reads_stdin_and_never_echoes_password(tmp_path) -> None:
    database_url = migrated_database_url(tmp_path)
    stdout = StringIO()
    stderr = StringIO()

    result = main(
        ["set-password", "  YLFEGO  ", "--password-stdin"],
        environ={"TRADING_AGENT_DATABASE_URL": database_url},
        stdin=StringIO("correct horse battery staple\n"),
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert "ylfego" in stdout.getvalue()
    assert "correct horse battery staple" not in stdout.getvalue()
    with create_engine(database_url).connect() as connection:
        user = connection.execute(select(UserRecord)).one()
    assert user.username == "ylfego"
    assert verify_password("correct horse battery staple", user.password_hash)


def test_set_password_uses_confirmed_interactive_prompt(tmp_path) -> None:
    database_url = migrated_database_url(tmp_path)
    prompts: list[str] = []
    passwords = iter(("first-secret", "first-secret"))

    result = main(
        ["set-password", "ylfego"],
        environ={"TRADING_AGENT_DATABASE_URL": database_url},
        getpass_fn=lambda prompt: (
            prompts.append(prompt),
            next(passwords),
        )[1],
    )

    assert result == 0
    assert prompts == ["Password: ", "Confirm password: "]


def test_set_password_rejects_empty_mismatched_and_extra_stdin(tmp_path) -> None:
    database_url = migrated_database_url(tmp_path)

    empty = main(
        ["set-password", "ylfego", "--password-stdin"],
        environ={"TRADING_AGENT_DATABASE_URL": database_url},
        stdin=StringIO("\n"),
        stderr=StringIO(),
    )
    extra = main(
        ["set-password", "ylfego", "--password-stdin"],
        environ={"TRADING_AGENT_DATABASE_URL": database_url},
        stdin=StringIO("secret\nunexpected\n"),
        stderr=StringIO(),
    )
    passwords = iter(("one", "two"))
    mismatch = main(
        ["set-password", "ylfego"],
        environ={"TRADING_AGENT_DATABASE_URL": database_url},
        getpass_fn=lambda _: next(passwords),
        stderr=StringIO(),
    )

    assert empty == extra == mismatch == 1


def test_enable_and_disable_update_existing_user(tmp_path) -> None:
    database_url = migrated_database_url(tmp_path)
    environment = {"TRADING_AGENT_DATABASE_URL": database_url}
    main(
        ["set-password", "ylfego", "--password-stdin"],
        environ=environment,
        stdin=StringIO("secret\n"),
    )

    assert main(["disable", "ylfego"], environ=environment) == 0
    with create_engine(database_url).connect() as connection:
        disabled = connection.execute(select(UserRecord.is_active)).scalar_one()
    assert disabled is False

    assert main(["enable", "ylfego"], environ=environment) == 0
    with create_engine(database_url).connect() as connection:
        enabled = connection.execute(select(UserRecord.is_active)).scalar_one()
    assert enabled is True


def test_enable_disable_missing_user_and_unmigrated_database_fail(tmp_path) -> None:
    database_url = migrated_database_url(tmp_path)
    stderr = StringIO()

    missing = main(
        ["disable", "missing"],
        environ={"TRADING_AGENT_DATABASE_URL": database_url},
        stderr=stderr,
    )
    unmigrated = main(
        ["set-password", "ylfego", "--password-stdin"],
        environ={
            "TRADING_AGENT_DATABASE_URL": (
                f"sqlite+pysqlite:///{tmp_path / 'unmigrated.db'}"
            )
        },
        stdin=StringIO("secret\n"),
        stderr=stderr,
    )

    assert missing == 1
    assert unmigrated == 1
    assert "does not exist" in stderr.getvalue()
    assert "alembic upgrade head" in stderr.getvalue()
