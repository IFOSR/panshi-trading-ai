from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from getpass import getpass
import os
import sys
from typing import TextIO

from sqlalchemy import inspect

from trading_agent.auth.passwords import hash_password
from trading_agent.auth.repository import AuthRepository
from trading_agent.db.base import build_engine, session_factory


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="panshi-user",
        description="Manage Panshi users in the configured SQLite database.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    set_password = subparsers.add_parser(
        "set-password",
        help="Create a user or replace its password.",
    )
    set_password.add_argument("username")
    set_password.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read exactly one password line from standard input.",
    )
    for command in ("enable", "disable"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("username")
    return parser


def _read_password(
    *,
    password_stdin: bool,
    stdin: TextIO,
    getpass_fn: Callable[[str], str],
) -> str:
    if password_stdin:
        lines = stdin.read().splitlines()
        if len(lines) != 1 or not lines[0]:
            raise ValueError("standard input must contain exactly one non-empty password")
        return lines[0]
    password = getpass_fn("Password: ")
    confirmation = getpass_fn("Confirm password: ")
    if not password:
        raise ValueError("password cannot be empty")
    if password != confirmation:
        raise ValueError("password confirmation does not match")
    return password


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    getpass_fn: Callable[[str], str] | None = None,
) -> int:
    args = _build_parser().parse_args(argv)
    environment = environ or os.environ
    input_stream = stdin or sys.stdin
    output_stream = stdout or sys.stdout
    error_stream = stderr or sys.stderr
    prompt = getpass_fn or getpass
    database_url = environment.get("TRADING_AGENT_DATABASE_URL", "")
    if not database_url:
        print("error: TRADING_AGENT_DATABASE_URL is not configured", file=error_stream)
        return 1

    engine = build_engine(database_url)
    inspector = inspect(engine)
    if not {"users", "auth_sessions"}.issubset(inspector.get_table_names()):
        print(
            "error: authentication schema does not exist; run alembic upgrade head",
            file=error_stream,
        )
        engine.dispose()
        return 1

    sessions = session_factory(engine)
    try:
        with sessions() as session:
            with session.begin():
                repository = AuthRepository(session)
                if args.command == "set-password":
                    password = _read_password(
                        password_stdin=args.password_stdin,
                        stdin=input_stream,
                        getpass_fn=prompt,
                    )
                    user = repository.set_password(
                        args.username,
                        hash_password(password),
                    )
                    print(
                        f"Password updated for {user['username']}",
                        file=output_stream,
                    )
                    return 0
                active = args.command == "enable"
                if not repository.set_active(args.username, active):
                    print(
                        f"error: user {args.username.strip().lower()} does not exist",
                        file=error_stream,
                    )
                    return 1
                state = "enabled" if active else "disabled"
                print(
                    f"User {args.username.strip().lower()} {state}",
                    file=output_stream,
                )
                return 0
    except ValueError as exc:
        print(f"error: {exc}", file=error_stream)
        return 1
    finally:
        engine.dispose()


def entrypoint() -> int:
    return main()


if __name__ == "__main__":
    raise SystemExit(entrypoint())
