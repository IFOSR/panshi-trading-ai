from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from typing import TextIO
from urllib.parse import urlsplit


API_HOST = "127.0.0.1"
API_PORT = 8000
WEB_HOST = "127.0.0.1"
WEB_BIND_HOST = "panshi.localhost"
WEB_PORT = 8989
SERVICE_ORDER = ("api", "web")
LOCAL_REQUIRED_SETTINGS = (
    "TRADING_AGENT_ENVIRONMENT",
    "TRADING_AGENT_ENABLE_ORDER_EXECUTION",
    "TRADING_AGENT_DATABASE_URL",
    "TRADING_AGENT_IMAGE_ROOT",
    "TRADING_AGENT_MARKET_DATA_PROVIDER",
    "TRADING_AGENT_PRIMARY_VISION_PROVIDER",
    "TRADING_AGENT_CODEX_MODEL",
    "TRADING_AGENT_CODEX_MODEL_PROVIDER",
    "TRADING_AGENT_CODEX_PROVIDER_BASE_URL",
    "TRADING_AGENT_CODEX_PROVIDER_ENV_KEY",
    "TRADING_AGENT_API_TOKEN",
    "TRADING_AGENT_PRIVACY_REVIEW_TOKEN",
)
LOCAL_NON_SECRET_DEFAULTS = {
    "TRADING_AGENT_ENVIRONMENT": "local",
    "TRADING_AGENT_ENABLE_ORDER_EXECUTION": "false",
    "TRADING_AGENT_PRIMARY_VISION_PROVIDER": "codex",
    "TRADING_AGENT_FALLBACK_VISION_PROVIDER": "kimi",
    "TRADING_AGENT_CODEX_MODEL": "gpt-5.6-sol",
    "TRADING_AGENT_CODEX_MODEL_PROVIDER": "code-cli",
    "TRADING_AGENT_CODEX_PROVIDER_BASE_URL": "https://www.code-cli.cn/v1",
    "TRADING_AGENT_CODEX_PROVIDER_ENV_KEY": "CODE_CLI_API_KEY",
    "TRADING_AGENT_KIMI_MODEL": "default",
    "TRADING_AGENT_KIMI_EXTERNAL_ISOLATION_VERIFIED": "false",
    "TRADING_AGENT_KIMI_ISOLATION_PROVIDER": "",
    "TRADING_AGENT_MARKET_DATA_PROVIDER": "free",
    "TRADING_AGENT_MARKET_DATA_HISTORY_LENGTH": "240",
    "TRADING_AGENT_MARKET_DATA_TIMEOUT_SECONDS": "10",
    "TRADING_AGENT_MARKET_DATA_VALIDATE_EXCHANGE_DAILY": "true",
    "TRADING_API_URL": f"http://{API_HOST}:{API_PORT}",
}
LEGACY_LOCAL_SETTINGS = (
    "TRADING_AGENT_WEB_USERNAME",
    "TRADING_AGENT_WEB_PASSWORD",
)


@dataclass(frozen=True)
class LocalPaths:
    project_root: Path
    runtime_root: Path
    environment_file: Path
    venv_root: Path
    venv_python: Path
    data_root: Path
    database_path: Path
    image_root: Path
    run_root: Path
    log_root: Path
    web_root: Path

    @classmethod
    def from_root(cls, root: Path) -> "LocalPaths":
        project_root = root.expanduser().resolve()
        runtime_root = project_root / ".local"
        venv_root = runtime_root / "venv"
        executable = "python.exe" if os.name == "nt" else "python"
        venv_python = (
            venv_root / "Scripts" / executable
            if os.name == "nt"
            else venv_root / "bin" / executable
        )
        data_root = runtime_root / "data"
        return cls(
            project_root=project_root,
            runtime_root=runtime_root,
            environment_file=runtime_root / "env",
            venv_root=venv_root,
            venv_python=venv_python,
            data_root=data_root,
            database_path=data_root / "trading-agent.db",
            image_root=data_root / "images",
            run_root=runtime_root / "run",
            log_root=runtime_root / "logs",
            web_root=project_root / "web",
        )

    def pid_file(self, service: str) -> Path:
        return self.run_root / f"{service}.pid"

    def metadata_file(self, service: str) -> Path:
        return self.run_root / f"{service}.json"

    def log_file(self, service: str) -> Path:
        return self.log_root / f"{service}.log"


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str
    required: bool = True


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_environment_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum() or key[0].isdigit():
            raise ValueError(f"{path}:{line_number}: invalid environment key")
        values[key] = value
    return values


def _write_private_environment(path: Path, values: Mapping[str, str]) -> None:
    for key, value in values.items():
        if "\n" in key or "\n" in value or "\r" in key or "\r" in value:
            raise ValueError("local environment values cannot contain newlines")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        "".join(f"{key}={value}\n" for key, value in values.items()),
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(path)
    path.chmod(0o600)


def _secure_runtime_directories(paths: LocalPaths) -> None:
    for directory in (
        paths.runtime_root,
        paths.data_root,
        paths.image_root,
        paths.run_root,
        paths.log_root,
    ):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)


def _validate_local_environment(values: Mapping[str, str]) -> None:
    missing = [key for key in LOCAL_REQUIRED_SETTINGS if not values.get(key)]
    if missing:
        raise ValueError(
            "missing required local settings: " + ", ".join(missing)
        )
    if values["TRADING_AGENT_ENVIRONMENT"].strip().lower() != "local":
        raise ValueError("TRADING_AGENT_ENVIRONMENT must be local")
    if values["TRADING_AGENT_ENABLE_ORDER_EXECUTION"].strip().lower() != "false":
        raise ValueError("TRADING_AGENT_ENABLE_ORDER_EXECUTION must be false")
    if "TEMPORAL_ADDRESS" in values:
        raise ValueError("TEMPORAL_ADDRESS is not allowed in local environment")
    database_url = values["TRADING_AGENT_DATABASE_URL"]
    if not database_url.startswith("sqlite+pysqlite:////"):
        raise ValueError("local database must use an absolute SQLite URL")
    image_root = Path(values["TRADING_AGENT_IMAGE_ROOT"])
    if not image_root.is_absolute():
        raise ValueError("local image root must be an absolute path")
    provider_env_key = values["TRADING_AGENT_CODEX_PROVIDER_ENV_KEY"]
    if not values.get(provider_env_key):
        raise ValueError(
            f"Codex provider credential {provider_env_key} is not configured"
        )


def _local_default_values(
    paths: LocalPaths,
    source_environment: Mapping[str, str],
    token_factory: Callable[[], str],
) -> dict[str, str]:
    values = {
        **LOCAL_NON_SECRET_DEFAULTS,
        "TRADING_AGENT_DATABASE_URL": (
            f"sqlite+pysqlite:///{paths.database_path.as_posix()}"
        ),
        "TRADING_AGENT_IMAGE_ROOT": str(paths.image_root),
        "TRADING_AGENT_API_TOKEN": token_factory(),
        "TRADING_AGENT_PRIVACY_REVIEW_TOKEN": token_factory(),
    }
    for key in (
        "CODE_CLI_API_KEY",
        "OPENAI_API_KEY",
        "TRADING_AGENT_TQSDK_USERNAME",
        "TRADING_AGENT_TQSDK_PASSWORD",
    ):
        if value := source_environment.get(key):
            values[key] = value
    return values


def initialize_local_environment(
    paths: LocalPaths,
    *,
    source_environment: Mapping[str, str] | None = None,
    token_factory: Callable[[], str] | None = None,
) -> dict[str, str]:
    _secure_runtime_directories(paths)
    if paths.environment_file.exists():
        paths.environment_file.chmod(0o600)
        values = _parse_environment_file(paths.environment_file)
        changed = False
        for key in LEGACY_LOCAL_SETTINGS:
            if key in values:
                del values[key]
                changed = True
        for key, value in LOCAL_NON_SECRET_DEFAULTS.items():
            if key not in values:
                values[key] = value
                changed = True
        _validate_local_environment(values)
        if changed:
            _write_private_environment(paths.environment_file, values)
        return values
    values = _local_default_values(
        paths,
        source_environment or os.environ,
        token_factory or (lambda: secrets.token_urlsafe(32)),
    )
    _write_private_environment(paths.environment_file, values)
    _validate_local_environment(values)
    return values


def build_process_environment(
    paths: LocalPaths,
    *,
    base_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
    local_values = _parse_environment_file(paths.environment_file)
    _validate_local_environment(local_values)
    environment = dict(base_environment or os.environ)
    environment.update(local_values)
    environment["TRADING_AGENT_ENVIRONMENT"] = "local"
    environment["TRADING_AGENT_ENABLE_ORDER_EXECUTION"] = "false"
    environment["TRADING_API_URL"] = f"http://{API_HOST}:{API_PORT}"
    source_root = str(paths.project_root / "src")
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{source_root}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else source_root
    )
    environment.pop("TEMPORAL_ADDRESS", None)
    return environment


def service_commands(paths: LocalPaths) -> dict[str, list[str]]:
    return {
        "api": [
            str(paths.venv_python),
            "-m",
            "uvicorn",
            "trading_agent.api.app:app",
            "--host",
            API_HOST,
            "--port",
            str(API_PORT),
        ],
        "web": [
            "npm",
            "run",
            "start",
            "--",
            "--hostname",
            WEB_BIND_HOST,
            "--port",
            str(WEB_PORT),
        ],
    }


def _run_checked(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str] | None = None,
) -> None:
    subprocess.run(
        list(command),
        cwd=cwd,
        env=dict(environment) if environment is not None else None,
        check=True,
    )


def _create_virtual_environment(paths: LocalPaths) -> None:
    configuration = paths.venv_root / "pyvenv.cfg"
    if configuration.is_file() and (
        "include-system-site-packages = true"
        in configuration.read_text(encoding="utf-8").lower()
    ):
        return
    arguments = [
        sys.executable,
        "-m",
        "venv",
        "--system-site-packages",
    ]
    if paths.venv_python.is_file():
        arguments.append("--upgrade")
    arguments.append(str(paths.venv_root))
    _run_checked(
        arguments,
        cwd=paths.project_root,
    )


def _ensure_python_dependencies(paths: LocalPaths) -> None:
    available, _ = _python_runtime_available(paths)
    if available:
        return
    _run_checked(
        [
            str(paths.venv_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-e",
            ".[dev]",
        ],
        cwd=paths.project_root,
    )


def _ensure_web_dependencies(paths: LocalPaths) -> bool:
    install_lock = paths.web_root / "node_modules" / ".package-lock.json"
    sources = (
        paths.web_root / "package.json",
        paths.web_root / "package-lock.json",
    )
    if install_lock.is_file():
        install_timestamp = install_lock.stat().st_mtime
        if all(
            not source.is_file() or source.stat().st_mtime <= install_timestamp
            for source in sources
        ):
            return False
    _run_checked(["npm", "ci", "--prefer-offline"], cwd=paths.web_root)
    return True


def _ensure_web_build(paths: LocalPaths, *, force: bool = False) -> None:
    build_id = paths.web_root / ".next" / "BUILD_ID"
    if not force and build_id.is_file():
        build_timestamp = build_id.stat().st_mtime
        source_roots = (
            paths.web_root / "app",
            paths.web_root / "components",
            paths.web_root / "lib",
        )
        source_files = (
            path
            for root in source_roots
            if root.is_dir()
            for path in root.rglob("*")
            if path.is_file()
        )
        configuration_files = (
            paths.web_root / "middleware.ts",
            paths.web_root / "next.config.ts",
            paths.web_root / "package.json",
            paths.web_root / "package-lock.json",
            paths.web_root / "tsconfig.json",
        )
        if all(
            path.stat().st_mtime <= build_timestamp
            for path in (*source_files, *configuration_files)
            if path.is_file()
        ):
            return
    _run_checked(["npm", "run", "build"], cwd=paths.web_root)


def _install_dependencies(paths: LocalPaths) -> None:
    _ensure_python_dependencies(paths)
    dependencies_changed = _ensure_web_dependencies(paths)
    _ensure_web_build(paths, force=dependencies_changed)


def _apply_migrations(paths: LocalPaths, environment: Mapping[str, str]) -> None:
    _run_checked(
        [str(paths.venv_python), "-m", "alembic", "upgrade", "head"],
        cwd=paths.project_root,
        environment=environment,
    )


def initialize_runtime(paths: LocalPaths) -> None:
    with _runtime_lock(paths):
        initialize_local_environment(paths)
        _create_virtual_environment(paths)
        _install_dependencies(paths)
        environment = build_process_environment(paths)
        _apply_migrations(paths, environment)


def _command_version(command: str, *arguments: str) -> tuple[bool, str]:
    executable = shutil.which(command)
    if executable is None:
        return False, f"{command} is not installed or not on PATH"
    try:
        completed = subprocess.run(
            [executable, *arguments],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{command} check failed: {exc}"
    output = (completed.stdout or completed.stderr).strip().splitlines()
    detail = output[-1] if output else f"exit {completed.returncode}"
    return completed.returncode == 0, detail


def _python_runtime_available(paths: LocalPaths) -> tuple[bool, str]:
    if not paths.venv_python.is_file():
        return False, f"{paths.venv_python} does not exist"
    modules = (
        "alembic",
        "akshare",
        "fastapi",
        "httpx",
        "numpy",
        "pydantic",
        "pydantic_settings",
        "sqlalchemy",
        "temporalio",
        "tqsdk",
        "trading_agent.auth.cli",
        "uvicorn",
    )
    script = f"""
import importlib.metadata
import importlib.util
import re
import sys

modules = {modules!r}
constraints = {{
    "akshare": ("1.18.75", "2"),
    "tqsdk": ("3.10.1", "4"),
}}
required_commands = {{"panshi-user", "trading-agent-local"}}

def version_tuple(value):
    parts = [int(part) for part in re.findall(r"\\d+", value)[:3]]
    return tuple((parts + [0, 0, 0])[:3])

missing = [
    name for name in modules
    if importlib.util.find_spec(name) is None
]
if missing:
    print("missing runtime modules: " + ", ".join(missing))
    sys.exit(1)

commands = {{
    entry.name
    for entry in importlib.metadata.entry_points(group="console_scripts")
}}
missing_commands = sorted(required_commands - commands)
if missing_commands:
    print("missing runtime commands: " + ", ".join(missing_commands))
    sys.exit(1)

incompatible = []
for distribution, (minimum, maximum) in constraints.items():
    installed = importlib.metadata.version(distribution)
    if not (
        version_tuple(minimum)
        <= version_tuple(installed)
        < version_tuple(maximum)
    ):
        incompatible.append(f"{{distribution}}=={{installed}}")
if incompatible:
    print("incompatible runtime modules: " + ", ".join(incompatible))
    sys.exit(1)
"""
    completed = subprocess.run(
        [
            str(paths.venv_python),
            "-c",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if completed.returncode == 0:
        return True, f"{paths.venv_python} can locate all runtime modules"
    detail = (completed.stderr or completed.stdout).strip().splitlines()
    return False, detail[-1] if detail else f"exit {completed.returncode}"


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _path_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


def _pid(paths: LocalPaths, service: str) -> int | None:
    try:
        return int(paths.pid_file(service).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


@contextmanager
def _runtime_lock(paths: LocalPaths):
    _secure_runtime_directories(paths)
    lock_path = paths.run_root / "lifecycle.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        lock_path.chmod(0o600)
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("local lifecycle command already in progress") from exc
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _process_start_time(pid: int) -> str | None:
    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    environment["LANG"] = "C"
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    start_time = " ".join(completed.stdout.split())
    return start_time or None


def _managed_process_alive(paths: LocalPaths, service: str, pid: int) -> bool:
    if not _process_alive(pid):
        return False
    try:
        metadata = json.loads(
            paths.metadata_file(service).read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return False
    if metadata.get("pid") != pid:
        return False
    expected_start_time = metadata.get("start_time")
    return (
        isinstance(expected_start_time, str)
        and bool(expected_start_time)
        and secrets.compare_digest(
            expected_start_time.encode("utf-8"),
            (_process_start_time(pid) or "").encode("utf-8"),
        )
    )


def service_status(paths: LocalPaths) -> dict[str, tuple[bool, int | None]]:
    result: dict[str, tuple[bool, int | None]] = {}
    for service in SERVICE_ORDER:
        pid = _pid(paths, service)
        alive = pid is not None and _managed_process_alive(paths, service, pid)
        if pid is not None and not alive:
            paths.pid_file(service).unlink(missing_ok=True)
            paths.metadata_file(service).unlink(missing_ok=True)
        result[service] = (alive, pid if alive else None)
    return result


def doctor_checks(paths: LocalPaths) -> list[CheckResult]:
    values: dict[str, str] = {}
    env_error: str | None = None
    try:
        values = _parse_environment_file(paths.environment_file)
        _validate_local_environment(values)
    except ValueError as exc:
        env_error = str(exc)
    python_ok = sys.version_info >= (3, 10)
    node_ok, node_detail = _command_version("node", "--version")
    npm_ok, npm_detail = _command_version("npm", "--version")
    codex_ok, codex_detail = _command_version("codex", "--version")
    runtime_ok, runtime_detail = _python_runtime_available(paths)
    current_status = service_status(paths)
    database_url = values.get("TRADING_AGENT_DATABASE_URL", "")
    image_root = Path(values.get("TRADING_AGENT_IMAGE_ROOT", "."))
    required_values = (
        "TRADING_AGENT_API_TOKEN",
        "TRADING_AGENT_PRIVACY_REVIEW_TOKEN",
    )
    missing_values = [key for key in required_values if not values.get(key)]
    checks = [
        CheckResult(
            "python",
            python_ok,
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        ),
        CheckResult("node", node_ok, node_detail),
        CheckResult("npm", npm_ok, npm_detail),
        CheckResult("codex", codex_ok, codex_detail),
        CheckResult(
            "virtualenv",
            runtime_ok,
            runtime_detail,
        ),
        CheckResult(
            "web build",
            (paths.web_root / ".next" / "BUILD_ID").is_file(),
            str(paths.web_root / ".next" / "BUILD_ID"),
        ),
        CheckResult(
            "local environment",
            paths.environment_file.is_file() and env_error is None,
            env_error or str(paths.environment_file),
        ),
        CheckResult(
            "secrets",
            not missing_values,
            "configured" if not missing_values else f"missing: {', '.join(missing_values)}",
        ),
        CheckResult(
            "inline analysis",
            "TEMPORAL_ADDRESS" not in values,
            "TEMPORAL_ADDRESS is absent"
            if "TEMPORAL_ADDRESS" not in values
            else "remove TEMPORAL_ADDRESS from the local environment",
        ),
        CheckResult(
            "order execution",
            values.get("TRADING_AGENT_ENABLE_ORDER_EXECUTION") == "false",
            values.get("TRADING_AGENT_ENABLE_ORDER_EXECUTION", "missing"),
        ),
        CheckResult(
            "sqlite",
            database_url.startswith("sqlite+pysqlite:////"),
            database_url or "missing",
        ),
        CheckResult(
            "image storage",
            image_root.is_absolute() and _path_writable(image_root),
            str(image_root),
        ),
        CheckResult(
            f"API port {API_PORT}",
            current_status["api"][0] or _port_available(API_HOST, API_PORT),
            "running locally" if current_status["api"][0] else "available",
        ),
        CheckResult(
            f"web port {WEB_PORT}",
            current_status["web"][0] or _port_available(WEB_HOST, WEB_PORT),
            "running locally" if current_status["web"][0] else "available",
        ),
        CheckResult(
            "Kimi fallback",
            values.get("TRADING_AGENT_KIMI_EXTERNAL_ISOLATION_VERIFIED") != "true",
            "disabled by default; Codex is primary",
            required=False,
        ),
    ]
    provider_env_key = values.get("TRADING_AGENT_CODEX_PROVIDER_ENV_KEY")
    if provider_env_key:
        checks.append(
            CheckResult(
                "Codex provider credential",
                bool(values.get(provider_env_key)),
                f"{provider_env_key} is configured"
                if values.get(provider_env_key)
                else f"{provider_env_key} is missing",
            )
        )
    return checks


def _print_checks(checks: Sequence[CheckResult], stream: TextIO) -> bool:
    success = True
    for check in checks:
        label = "OK" if check.ok else ("WARN" if not check.required else "FAIL")
        print(f"[{label}] {check.name}: {check.detail}", file=stream)
        if check.required and not check.ok:
            success = False
    return success


def _wait_for_url(
    url: str,
    timeout_seconds: float = 30.0,
    *,
    expected_statuses: set[int] | frozenset[int] = frozenset({200}),
) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname is None:
        raise ValueError(f"unsupported readiness URL: {url}")
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        connection = HTTPConnection(parsed.hostname, port, timeout=1)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            if response.status in expected_statuses:
                return True
        except OSError:
            time.sleep(0.25)
        finally:
            connection.close()
    return False


def _start_service(
    paths: LocalPaths,
    service: str,
    command: Sequence[str],
    environment: Mapping[str, str],
) -> int:
    cwd = paths.web_root if service == "web" else paths.project_root
    log_path = paths.log_file(service)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab", buffering=0) as log:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    paths.pid_file(service).write_text(f"{process.pid}\n", encoding="utf-8")
    paths.pid_file(service).chmod(0o600)
    start_time = _process_start_time(process.pid)
    if start_time is None:
        process.terminate()
        raise RuntimeError(f"could not identify started {service} process")
    paths.metadata_file(service).write_text(
        json.dumps(
            {
                "pid": process.pid,
                "start_time": start_time,
                "command": list(command),
                "cwd": str(cwd),
                "started_at": time.time(),
            },
            ensure_ascii=True,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    paths.metadata_file(service).chmod(0o600)
    return process.pid


def start_runtime(paths: LocalPaths) -> None:
    with _runtime_lock(paths):
        _start_runtime_unlocked(paths)


def _start_runtime_unlocked(paths: LocalPaths) -> None:
    initialize_local_environment(paths)
    environment = build_process_environment(paths)
    _ensure_web_build(paths)
    checks = doctor_checks(paths)
    if not _print_checks(checks, sys.stdout):
        raise RuntimeError("local runtime preflight failed")
    _apply_migrations(paths, environment)
    status = service_status(paths)
    commands = service_commands(paths)
    started: list[str] = []
    try:
        for service in SERVICE_ORDER:
            if status[service][0]:
                continue
            _start_service(paths, service, commands[service], environment)
            started.append(service)
        if not _wait_for_url(
            f"http://{API_HOST}:{API_PORT}/openapi.json",
            expected_statuses={200},
        ):
            raise RuntimeError(
                f"API failed to become ready; see {paths.log_file('api')}"
            )
        if not _wait_for_url(
            f"http://{WEB_HOST}:{WEB_PORT}/login",
            expected_statuses={200},
        ):
            raise RuntimeError(
                f"web failed to become ready; see {paths.log_file('web')}"
            )
    except Exception:
        for service in reversed(started):
            _stop_service(paths, service)
        raise


def _stop_service(paths: LocalPaths, service: str, timeout_seconds: float = 10.0) -> None:
    pid = _pid(paths, service)
    if pid is None or not _managed_process_alive(paths, service, pid):
        paths.pid_file(service).unlink(missing_ok=True)
        paths.metadata_file(service).unlink(missing_ok=True)
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + timeout_seconds
    while _process_group_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    if _process_group_alive(pid):
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    paths.pid_file(service).unlink(missing_ok=True)
    paths.metadata_file(service).unlink(missing_ok=True)


def stop_runtime(paths: LocalPaths) -> None:
    with _runtime_lock(paths):
        _stop_runtime_unlocked(paths)


def _stop_runtime_unlocked(paths: LocalPaths) -> None:
    for service in reversed(SERVICE_ORDER):
        _stop_service(paths, service)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trading-agent-local",
        description="Manage the Docker-free local Trading Agent runtime.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=_project_root(),
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "command",
        choices=("init", "doctor", "start", "stop", "status", "restart"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    paths = LocalPaths.from_root(args.project_root)
    try:
        if args.command == "init":
            initialize_runtime(paths)
            print(f"Local runtime initialized at {paths.runtime_root}")
            return 0
        if args.command == "doctor":
            with _runtime_lock(paths):
                checks = doctor_checks(paths)
            return 0 if _print_checks(checks, sys.stdout) else 1
        if args.command == "start":
            start_runtime(paths)
            print(f"Trading Agent API: http://{API_HOST}:{API_PORT}/docs")
            print(f"Trading Agent web: http://{WEB_HOST}:{WEB_PORT}")
            return 0
        if args.command == "stop":
            stop_runtime(paths)
            print("Local Trading Agent stopped")
            return 0
        if args.command == "restart":
            with _runtime_lock(paths):
                _stop_runtime_unlocked(paths)
                _start_runtime_unlocked(paths)
            print(f"Trading Agent web: http://{WEB_HOST}:{WEB_PORT}")
            return 0
        with _runtime_lock(paths):
            status = service_status(paths)
        for service in SERVICE_ORDER:
            running, pid = status[service]
            print(
                f"{service}: {'running' if running else 'stopped'}"
                + (f" (pid {pid})" if pid else "")
            )
        return 0 if all(item[0] for item in status.values()) else 1
    except (OSError, subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
