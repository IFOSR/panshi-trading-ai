import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import signal
import subprocess
from threading import Thread

import pytest

from trading_agent.api.app import create_app
from trading_agent.local_runtime import (
    CheckResult,
    LocalPaths,
    _create_virtual_environment,
    _ensure_python_dependencies,
    _managed_process_alive,
    _process_start_time,
    _runtime_lock,
    _secure_runtime_directories,
    _start_runtime_unlocked,
    _stop_service,
    _wait_for_url,
    build_process_environment,
    initialize_local_environment,
    main,
    service_commands,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = (PROJECT_ROOT / "docs" / "runbook.md").read_text(encoding="utf-8")
LOCAL_ENV_EXAMPLE = (PROJECT_ROOT / ".env.local.example").read_text(encoding="utf-8")
PYPROJECT = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
GITIGNORE = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
HOME_PAGE = (PROJECT_ROOT / "web" / "app" / "page.tsx").read_text(
    encoding="utf-8"
)


def test_local_init_creates_private_absolute_environment(tmp_path: Path) -> None:
    paths = LocalPaths.from_root(tmp_path)

    values = initialize_local_environment(
        paths,
        source_environment={"CODE_CLI_API_KEY": "local-provider-key"},
        token_factory=iter(("api-secret", "privacy-secret")).__next__,
    )

    assert values["TRADING_AGENT_ENVIRONMENT"] == "local"
    assert values["TRADING_AGENT_ENABLE_ORDER_EXECUTION"] == "false"
    assert values["TRADING_AGENT_DATABASE_URL"] == (
        f"sqlite+pysqlite:///{paths.database_path.as_posix()}"
    )
    assert values["TRADING_AGENT_IMAGE_ROOT"] == str(paths.image_root)
    assert values["TRADING_AGENT_MARKET_DATA_PROVIDER"] == "free"
    assert values["TRADING_AGENT_API_TOKEN"] == "api-secret"
    assert "TRADING_AGENT_WEB_USERNAME" not in values
    assert "TRADING_AGENT_WEB_PASSWORD" not in values
    assert values["TRADING_AGENT_PRIVACY_REVIEW_TOKEN"] == "privacy-secret"
    assert values["CODE_CLI_API_KEY"] == "local-provider-key"
    assert "TEMPORAL_ADDRESS" not in values
    assert paths.environment_file.stat().st_mode & 0o777 == 0o600
    for directory in (
        paths.runtime_root,
        paths.data_root,
        paths.image_root,
        paths.run_root,
        paths.log_root,
    ):
        assert directory.stat().st_mode & 0o777 == 0o700


def test_local_init_preserves_existing_operator_configuration(tmp_path: Path) -> None:
    paths = LocalPaths.from_root(tmp_path)
    original = initialize_local_environment(
        paths,
        source_environment={"CODE_CLI_API_KEY": "operator-provider-key"},
        token_factory=iter(
            ("operator-owned", "operator-password", "operator-privacy")
        ).__next__,
    )

    values = initialize_local_environment(
        paths,
        source_environment={},
        token_factory=lambda: "must-not-be-used",
    )

    assert values == original
    assert values["TRADING_AGENT_API_TOKEN"] == "operator-owned"


def test_local_init_removes_legacy_web_credentials(tmp_path: Path) -> None:
    paths = LocalPaths.from_root(tmp_path)
    values = initialize_local_environment(
        paths,
        source_environment={"CODE_CLI_API_KEY": "operator-provider-key"},
        token_factory=iter(("api-secret", "privacy-secret")).__next__,
    )
    values["TRADING_AGENT_WEB_USERNAME"] = "operator"
    values["TRADING_AGENT_WEB_PASSWORD"] = "legacy-password"
    paths.environment_file.write_text(
        "".join(f"{key}={value}\n" for key, value in values.items()),
        encoding="utf-8",
    )

    migrated = initialize_local_environment(paths)

    assert "TRADING_AGENT_WEB_USERNAME" not in migrated
    assert "TRADING_AGENT_WEB_PASSWORD" not in migrated
    assert "TRADING_AGENT_WEB_USERNAME" not in paths.environment_file.read_text(
        encoding="utf-8"
    )


def test_local_init_rejects_incomplete_existing_environment(tmp_path: Path) -> None:
    paths = LocalPaths.from_root(tmp_path)
    paths.runtime_root.mkdir(parents=True)
    paths.environment_file.write_text(
        "TRADING_AGENT_API_TOKEN=operator-owned\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing required local settings"):
        initialize_local_environment(paths)


def test_local_runtime_repairs_existing_directory_permissions(tmp_path: Path) -> None:
    paths = LocalPaths.from_root(tmp_path)
    for directory in (
        paths.runtime_root,
        paths.data_root,
        paths.image_root,
        paths.run_root,
        paths.log_root,
    ):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o755)

    _secure_runtime_directories(paths)

    for directory in (
        paths.runtime_root,
        paths.data_root,
        paths.image_root,
        paths.run_root,
        paths.log_root,
    ):
        assert directory.stat().st_mode & 0o777 == 0o700


def test_local_process_environment_forces_inline_analysis(tmp_path: Path) -> None:
    paths = LocalPaths.from_root(tmp_path)
    paths.runtime_root.mkdir(parents=True)
    paths.environment_file.write_text(
        "\n".join(
            (
                "TRADING_AGENT_ENVIRONMENT=local",
                "TRADING_AGENT_ENABLE_ORDER_EXECUTION=false",
                "TRADING_AGENT_API_TOKEN=secret",
                "TRADING_AGENT_PRIVACY_REVIEW_TOKEN=privacy",
                "TRADING_AGENT_DATABASE_URL=sqlite+pysqlite:////tmp/local.db",
                    "TRADING_AGENT_IMAGE_ROOT=/tmp/local-images",
                    "TRADING_AGENT_MARKET_DATA_PROVIDER=free",
                    "TRADING_AGENT_PRIMARY_VISION_PROVIDER=codex",
                "TRADING_AGENT_CODEX_MODEL=gpt-5.6-sol",
                "TRADING_AGENT_CODEX_MODEL_PROVIDER=code-cli",
                "TRADING_AGENT_CODEX_PROVIDER_BASE_URL=https://provider.example/v1",
                "TRADING_AGENT_CODEX_PROVIDER_ENV_KEY=CODE_CLI_API_KEY",
                "CODE_CLI_API_KEY=test-key",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    environment = build_process_environment(
        paths,
        base_environment={
            "PATH": os.environ.get("PATH", ""),
            "TEMPORAL_ADDRESS": "temporal.example:7233",
        },
    )

    assert environment["TRADING_AGENT_ENVIRONMENT"] == "local"
    assert environment["TRADING_API_URL"] == "http://127.0.0.1:8000"
    assert environment["PYTHONPATH"].split(os.pathsep)[0] == str(paths.project_root / "src")
    assert "TEMPORAL_ADDRESS" not in environment


def test_local_virtualenv_reuses_installed_machine_dependencies(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    captured: list[list[str]] = []

    monkeypatch.setattr(
        "trading_agent.local_runtime._run_checked",
        lambda command, **kwargs: captured.append(list(command)),
    )

    _create_virtual_environment(paths)

    assert captured == [
        [
            os.sys.executable,
            "-m",
            "venv",
            "--system-site-packages",
            str(paths.venv_root),
        ]
    ]


def test_local_init_skips_pip_when_runtime_dependencies_are_available(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        "trading_agent.local_runtime._python_runtime_available",
        lambda _: (True, "available"),
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime._run_checked",
        lambda command, **kwargs: commands.append(list(command)),
    )

    _ensure_python_dependencies(paths)

    assert commands == []


def test_local_init_installs_python_dependencies_only_when_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        "trading_agent.local_runtime._python_runtime_available",
        lambda _: (False, "fastapi is missing"),
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime._run_checked",
        lambda command, **kwargs: commands.append(list(command)),
    )

    _ensure_python_dependencies(paths)

    assert commands == [
        [
            str(paths.venv_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-e",
            ".[dev]",
        ]
    ]


def test_local_services_use_only_api_web_sqlite_and_codex(tmp_path: Path) -> None:
    paths = LocalPaths.from_root(tmp_path)

    commands = service_commands(paths)
    flattened = " ".join(
        part
        for command in commands.values()
        for part in command
    ).lower()

    assert set(commands) == {"api", "web"}
    assert commands["api"][0] == str(paths.venv_python)
    assert "uvicorn" in commands["api"]
    assert commands["web"][:3] == ["npm", "run", "start"]
    assert "docker" not in flattened
    assert "temporal" not in flattened
    assert "worker" not in flattened


def test_local_runtime_declares_free_market_data_dependencies() -> None:
    assert '"akshare>=1.18.75,<2"' in PYPROJECT
    assert '"bottleneck>=1.3.6"' in PYPROJECT
    assert '"tqsdk>=3.10.1,<4"' in PYPROJECT


def test_local_runtime_installs_sqlite_user_administration_cli() -> None:
    assert 'panshi-user = "trading_agent.auth.cli:entrypoint"' in PYPROJECT
    assert "TRADING_AGENT_USER_PASSWORD" not in LOCAL_ENV_EXAMPLE


def test_runtime_dependency_check_does_not_import_heavy_market_modules(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    paths.venv_python.parent.mkdir(parents=True)
    paths.venv_python.write_text("", encoding="utf-8")
    captured: list[list[str]] = []

    def fake_run(command, **kwargs):
        captured.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("trading_agent.local_runtime.subprocess.run", fake_run)

    available, _ = __import__(
        "trading_agent.local_runtime",
        fromlist=["_python_runtime_available"],
    )._python_runtime_available(paths)

    assert available is True
    script = captured[0][2]
    assert "importlib.util.find_spec" in script
    assert '"panshi-user"' in script
    assert "console_scripts" in script
    assert "import akshare" not in script
    assert "import tqsdk" not in script


def test_runtime_dependency_check_validates_market_package_versions(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    paths.venv_python.parent.mkdir(parents=True)
    paths.venv_python.write_text("", encoding="utf-8")
    captured: list[list[str]] = []

    def fake_run(command, **kwargs):
        captured.append(list(command))
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="incompatible runtime modules: akshare==1.17.0",
            stderr="",
        )

    monkeypatch.setattr("trading_agent.local_runtime.subprocess.run", fake_run)

    available, detail = __import__(
        "trading_agent.local_runtime",
        fromlist=["_python_runtime_available"],
    )._python_runtime_available(paths)

    assert available is False
    assert detail == "incompatible runtime modules: akshare==1.17.0"
    script = captured[0][2]
    assert "importlib.metadata.version" in script
    assert "1.18.75" in script
    assert "3.10.1" in script
def test_managed_process_rejects_reused_pid(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    paths.run_root.mkdir(parents=True)
    paths.pid_file("api").write_text(f"{os.getpid()}\n", encoding="utf-8")
    paths.metadata_file("api").write_text(
        '{"pid": 1, "start_time": "different process"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime._process_start_time",
        lambda pid: "current process",
    )

    assert _managed_process_alive(paths, "api", os.getpid()) is False


def test_managed_process_accepts_non_ascii_start_time(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    paths.run_root.mkdir(parents=True)
    paths.metadata_file("api").write_text(
        f'{{"pid": {os.getpid()}, "start_time": "二 7/21 11:36:44 2026"}}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime._process_alive",
        lambda _: True,
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime._process_start_time",
        lambda _: "二 7/21 11:36:44 2026",
    )

    assert _managed_process_alive(paths, "api", os.getpid()) is True


def test_process_start_time_uses_a_stable_locale(monkeypatch) -> None:
    captured_environment: dict[str, str] = {}

    def run(*_args, **kwargs):
        captured_environment.update(kwargs["env"])
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="Tue Jul 21 11:36:44 2026\n",
        )

    monkeypatch.setattr(
        "trading_agent.local_runtime.subprocess.run",
        run,
    )

    assert _process_start_time(123) == "Tue Jul 21 11:36:44 2026"
    assert captured_environment["LC_ALL"] == "C"
    assert captured_environment["LANG"] == "C"


def test_runtime_lock_rejects_concurrent_lifecycle_command(tmp_path: Path) -> None:
    paths = LocalPaths.from_root(tmp_path)
    _secure_runtime_directories(paths)

    with _runtime_lock(paths):
        with pytest.raises(RuntimeError, match="already in progress"):
            with _runtime_lock(paths):
                pass


def test_doctor_command_respects_lifecycle_lock(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    called = False

    def checks(_paths: LocalPaths) -> list[CheckResult]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr("trading_agent.local_runtime.doctor_checks", checks)

    with _runtime_lock(paths):
        result = main(
            [
                "--project-root",
                str(paths.project_root),
                "doctor",
            ]
        )

    assert result == 1
    assert called is False


def test_stop_kills_remaining_process_group_after_leader_exits(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    paths.run_root.mkdir(parents=True)
    paths.pid_file("web").write_text("12345\n", encoding="utf-8")
    paths.metadata_file("web").write_text(
        '{"pid": 12345, "start_time": "start"}\n',
        encoding="utf-8",
    )
    managed_checks = iter((True, False))
    signals: list[int] = []

    monkeypatch.setattr(
        "trading_agent.local_runtime._managed_process_alive",
        lambda *_: next(managed_checks, False),
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime._process_group_alive",
        lambda _: True,
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime.os.killpg",
        lambda pid, sent_signal: signals.append(sent_signal),
    )

    _stop_service(paths, "web", timeout_seconds=0)

    assert signals == [signal.SIGTERM, signal.SIGKILL]


def test_api_uses_configured_local_image_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    image_root = tmp_path / "runtime" / "images"
    monkeypatch.setenv("TRADING_AGENT_IMAGE_ROOT", str(image_root))

    app = create_app(
        database_url="sqlite+pysqlite:///:memory:",
        vision_provider=None,
        environment="test",
    )

    assert app.state.image_root == image_root
    assert image_root.is_dir()


def test_local_runtime_is_the_primary_documented_entrypoint() -> None:
    assert "./bin/trading-agent-local init" in RUNBOOK
    assert "./bin/trading-agent-local start" in RUNBOOK
    assert "./bin/trading-agent-local doctor" in RUNBOOK
    assert "docker compose" not in RUNBOOK.lower()
    assert "trading-agent-local = " in PYPROJECT
    assert ".local/" in GITIGNORE


def test_runbook_documents_sqlite_user_authentication_operations() -> None:
    for required in (
        "panshi-user set-password",
        "panshi-user disable",
        "panshi-user enable",
        "12 小时",
        "SQLite 备份",
        "迁移到其他服务器",
        "密码轮换",
        "会话失效",
    ):
        assert required in RUNBOOK
    assert "Web 本地访问无需登录" not in RUNBOOK
    assert "TRADING_AGENT_USER_PASSWORD" not in RUNBOOK


def test_local_runtime_uses_web_port_8989_without_changing_api_port(
    tmp_path: Path,
) -> None:
    commands = service_commands(LocalPaths.from_root(tmp_path))

    assert commands["api"][-1] == "8000"
    assert commands["web"][-1] == "8989"


def test_production_homepage_loads_strategy_catalog_at_request_time() -> None:
    assert 'export const dynamic = "force-dynamic";' in HOME_PAGE


def test_root_startup_script_exposes_only_supported_lifecycle_commands() -> None:
    script = PROJECT_ROOT / "trading-agent.sh"

    assert script.is_file()
    assert os.access(script, os.X_OK)

    script_text = script.read_text(encoding="utf-8")
    assert 'case "${1-}" in' in script_text
    assert "start|stop|restart)" in script_text

    for arguments in ((), ("status",), ("start", "extra")):
        result = subprocess.run(
            [str(script), *arguments],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "Usage:" in result.stderr


def test_playwright_keeps_isolated_test_web_port() -> None:
    config = (PROJECT_ROOT / "web" / "playwright.config.ts").read_text(
        encoding="utf-8"
    )

    assert "npm run dev -- --port 3107" in config
    assert 'port: 3107' in config
    assert 'baseURL: "http://127.0.0.1:3107"' in config
    assert "httpCredentials" not in config
    assert "TRADING_AGENT_WEB_USERNAME" not in config
    assert "TRADING_AGENT_WEB_PASSWORD" not in config
    middleware = (PROJECT_ROOT / "web" / "middleware.ts").read_text(
        encoding="utf-8"
    )
    assert "Basic " not in middleware
    assert "Local access only" in middleware


def test_local_start_rebuilds_web_when_production_build_is_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(
        "trading_agent.local_runtime._run_checked",
        lambda command, **kwargs: commands.append(list(command)),
    )

    from trading_agent.local_runtime import _ensure_web_build

    _ensure_web_build(paths)

    assert commands == [["npm", "run", "build"]]


def test_local_start_does_not_rebuild_an_existing_web_build(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    build_id = paths.web_root / ".next" / "BUILD_ID"
    build_id.parent.mkdir(parents=True)
    build_id.write_text("test-build\n", encoding="utf-8")
    commands: list[list[str]] = []
    monkeypatch.setattr(
        "trading_agent.local_runtime._run_checked",
        lambda command, **kwargs: commands.append(list(command)),
    )

    from trading_agent.local_runtime import _ensure_web_build

    _ensure_web_build(paths)

    assert commands == []


def test_local_start_rebuilds_when_web_sources_are_newer_than_build(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    source = paths.web_root / "app" / "page.tsx"
    source.parent.mkdir(parents=True)
    source.write_text("export default function Page() { return null; }\n")
    build_id = paths.web_root / ".next" / "BUILD_ID"
    build_id.parent.mkdir(parents=True)
    build_id.write_text("test-build\n", encoding="utf-8")
    os.utime(build_id, (1, 1))
    commands: list[list[str]] = []
    monkeypatch.setattr(
        "trading_agent.local_runtime._run_checked",
        lambda command, **kwargs: commands.append(list(command)),
    )

    from trading_agent.local_runtime import _ensure_web_build

    _ensure_web_build(paths)

    assert commands == [["npm", "run", "build"]]


def test_doctor_requires_a_real_next_production_build(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    paths.runtime_root.mkdir(parents=True)
    paths.environment_file.write_text(
        "\n".join(
            (
                "TRADING_AGENT_ENVIRONMENT=local",
                "TRADING_AGENT_ENABLE_ORDER_EXECUTION=false",
                "TRADING_AGENT_API_TOKEN=secret",
                "TRADING_AGENT_PRIVACY_REVIEW_TOKEN=privacy",
                f"TRADING_AGENT_DATABASE_URL=sqlite+pysqlite:///{paths.database_path}",
                f"TRADING_AGENT_IMAGE_ROOT={paths.image_root}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (paths.web_root / ".next").mkdir(parents=True)
    monkeypatch.setattr(
        "trading_agent.local_runtime._command_version",
        lambda *args: (True, "available"),
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime._python_runtime_available",
        lambda _: (True, "available"),
    )

    from trading_agent.local_runtime import doctor_checks

    checks: dict[str, CheckResult] = {
        check.name: check for check in doctor_checks(paths)
    }

    assert checks["web build"].ok is False


def test_playwright_uses_an_isolated_next_build_directory() -> None:
    config = (PROJECT_ROOT / "web" / "playwright.config.ts").read_text(
        encoding="utf-8"
    )
    next_config = (PROJECT_ROOT / "web" / "next.config.ts").read_text(
        encoding="utf-8"
    )

    assert "NEXT_DIST_DIR=.next-playwright" in config
    assert "process.env.NEXT_DIST_DIR" in next_config
    assert "web/.next-playwright/" in GITIGNORE


def test_local_environment_template_disables_distributed_runtime() -> None:
    assert "TRADING_AGENT_ENVIRONMENT=local" in LOCAL_ENV_EXAMPLE
    assert "TRADING_AGENT_ENABLE_ORDER_EXECUTION=false" in LOCAL_ENV_EXAMPLE
    assert "TRADING_AGENT_PRIMARY_VISION_PROVIDER=codex" in LOCAL_ENV_EXAMPLE
    assert "TRADING_AGENT_KIMI_EXTERNAL_ISOLATION_VERIFIED=false" in LOCAL_ENV_EXAMPLE
    assert "TRADING_AGENT_WEB_USERNAME" not in LOCAL_ENV_EXAMPLE
    assert "TRADING_AGENT_WEB_PASSWORD" not in LOCAL_ENV_EXAMPLE
    assert "TRADING_AGENT_USER_PASSWORD" not in LOCAL_ENV_EXAMPLE
    assert "TEMPORAL_ADDRESS" not in LOCAL_ENV_EXAMPLE
    assert "postgresql" not in LOCAL_ENV_EXAMPLE.lower()
    assert "redis" not in LOCAL_ENV_EXAMPLE.lower()
    assert "minio" not in LOCAL_ENV_EXAMPLE.lower()


def test_readiness_requires_an_expected_status() -> None:
    class AuthenticatedHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Trading Agent"')
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), AuthenticatedHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert not _wait_for_url(
            f"http://127.0.0.1:{server.server_port}/",
            timeout_seconds=0.5,
            expected_statuses={200},
        )
        assert _wait_for_url(
            f"http://127.0.0.1:{server.server_port}/",
            timeout_seconds=0.5,
            expected_statuses={200, 401},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_local_start_uses_the_public_login_page_for_readiness(
    monkeypatch,
    tmp_path: Path,
) -> None:
    paths = LocalPaths.from_root(tmp_path)
    readiness_checks: list[tuple[str, set[int]]] = []

    monkeypatch.setattr(
        "trading_agent.local_runtime.initialize_local_environment",
        lambda _: {},
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime.build_process_environment",
        lambda _: {},
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime._ensure_web_build",
        lambda _: None,
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime.doctor_checks",
        lambda _: [],
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime._print_checks",
        lambda *_: True,
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime._apply_migrations",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime.service_status",
        lambda _: {"api": (False, None), "web": (False, None)},
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime.service_commands",
        lambda _: {"api": ["api"], "web": ["web"]},
    )
    monkeypatch.setattr(
        "trading_agent.local_runtime._start_service",
        lambda *_: 1,
    )

    def wait_for_url(
        url: str,
        *,
        expected_statuses: set[int],
        **_: object,
    ) -> bool:
        readiness_checks.append((url, expected_statuses))
        return True

    monkeypatch.setattr(
        "trading_agent.local_runtime._wait_for_url",
        wait_for_url,
    )

    _start_runtime_unlocked(paths)

    assert readiness_checks[-1] == (
        "http://127.0.0.1:8989/login",
        {200},
    )
