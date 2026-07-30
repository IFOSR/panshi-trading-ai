from hashlib import sha256
from contextlib import contextmanager
import fcntl
import json
import logging
import os
from pathlib import Path
import shutil
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
import secrets
from threading import Event, RLock, Thread
from typing import Iterator
from uuid import NAMESPACE_URL, uuid4, uuid5

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.exc import IntegrityError
from temporalio.client import Client
from temporalio.common import WorkflowIDConflictPolicy

from trading_agent.agents.factory import configured_agent_backend_registry
from trading_agent.agents.models import AgentRuntime
from trading_agent.agents.registry import (
    AgentBackendRegistry,
    AgentBackendUnavailable,
)
from trading_agent.config import Settings
from trading_agent.auth.service import AuthService, InvalidCredentials, InvalidSession
from trading_agent.conversation.models import ConversationReply
from trading_agent.conversation.service import ConversationService
from trading_agent.db.base import Base, build_engine, session_factory
from trading_agent.db.repositories import (
    CaseRepository,
    CaseVersionConflict,
    CommandInProgress,
)
from trading_agent.domain.enums import ImageRole, PositionDirection
from trading_agent.market.resolver import (
    MarketDataResolver,
    configured_market_data_resolver,
)
from trading_agent.providers.base import (
    ClarificationProvider,
    ConversationProvider,
    ProviderResponseError,
    ProviderUnavailable,
    VisionProvider,
)
from trading_agent.services.analysis import build_analysis_payload
from trading_agent.services.clarification import ClarificationService
from trading_agent.services.evidence_pipeline import extract_case_evidence
from trading_agent.services.user_input import parse_user_message
from trading_agent.vision.image_quality import (
    MAX_IMAGE_BYTES,
    validate_original_image_content,
)
from trading_agent.vision.privacy import assess_upload_privacy
from trading_agent.workflows.activities import AnalysisCommand
from trading_agent.workflows.analysis import AnalysisWorkflow
from trading_agent.workflows.worker import DurableAnalysisWorkflow, TASK_QUEUE
from trading_agent.strategies.registry import (
    StrategyNotFound,
    StrategyRegistry,
    configured_strategy_registry,
)


TemporalExecutor = Callable[[AnalysisCommand], Awaitable[dict[str, object]]]
QuarantinedImageDirectory = tuple[Path, Path]
logger = logging.getLogger(__name__)


class _CaseMutationCoordinator:
    def __init__(self, image_root: Path) -> None:
        self.image_root = image_root.resolve()
        self.thread_lock = RLock()
        self.lock_path = (
            self.image_root.parent
            / f".{self.image_root.name}.case-mutations.lock"
        )

    @contextmanager
    def locked(self) -> Iterator[None]:
        with self.thread_lock:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+b") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


class _DeletionCleanupRetrier:
    def __init__(self, coordinator: _CaseMutationCoordinator) -> None:
        self.coordinator = coordinator
        self.worker_lock = RLock()
        self.worker: Thread | None = None
        self.wake = Event()

    def schedule(self, _operation_root: Path) -> None:
        self.wake.set()
        with self.worker_lock:
            if self.worker is not None and self.worker.is_alive():
                return
            self.worker = Thread(
                target=self._run,
                name="deletion-cleanup-worker",
                daemon=True,
            )
            self.worker.start()

    def _operation_roots(self) -> list[Path]:
        trash_root = self.coordinator.image_root / ".trash"
        if not trash_root.is_dir():
            return []
        return sorted(path for path in trash_root.iterdir() if path.is_dir())

    def _run(self) -> None:
        delay_seconds = 0.05
        while True:
            operation_roots = self._operation_roots()
            if not operation_roots:
                with self.worker_lock:
                    operation_roots = self._operation_roots()
                    if not operation_roots:
                        self.worker = None
                        return
                continue
            cleanup_failed = False
            for operation_root in operation_roots:
                try:
                    with self.coordinator.locked():
                        _purge_quarantined_images(operation_root)
                except OSError:
                    cleanup_failed = True
                    logger.exception(
                        "retrying deferred deletion cleanup for %s",
                        operation_root,
                    )
            if cleanup_failed:
                self.wake.wait(delay_seconds)
                self.wake.clear()
                delay_seconds = min(delay_seconds * 2, 30.0)
            else:
                delay_seconds = 0.05


def _write_deletion_manifest(
    operation_root: Path,
    case_ids: list[str],
    state: str,
) -> None:
    operation_root.mkdir(parents=True, exist_ok=True)
    manifest_path = operation_root / "operation.json"
    temporary_path = operation_root / "operation.json.tmp"
    temporary_path.write_text(
        json.dumps(
            {
                "version": 1,
                "case_ids": case_ids,
                "state": state,
            },
            ensure_ascii=True,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary_path.replace(manifest_path)


def _read_deletion_case_ids(operation_root: Path) -> list[str]:
    manifest_path = operation_root / "operation.json"
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        case_ids = payload.get("case_ids")
        if not isinstance(case_ids, list) or not all(
            isinstance(case_id, str) for case_id in case_ids
        ):
            raise ValueError(f"invalid deletion manifest: {manifest_path}")
        return case_ids
    legacy_directories = [
        path.name
        for path in operation_root.iterdir()
        if path.is_dir() and path.name != "images"
    ]
    return legacy_directories


def _restore_quarantined_images(
    operation_root: Path,
    moved: list[QuarantinedImageDirectory],
) -> None:
    for original, quarantined in reversed(moved):
        if quarantined.exists():
            original.parent.mkdir(parents=True, exist_ok=True)
            quarantined.replace(original)
    shutil.rmtree(operation_root, ignore_errors=True)
    trash_root = operation_root.parent
    if trash_root.is_dir() and not any(trash_root.iterdir()):
        trash_root.rmdir()


def _quarantine_case_images(
    image_root: Path,
    case_ids: list[str],
) -> tuple[Path, list[QuarantinedImageDirectory]]:
    resolved_root = image_root.resolve()
    operation_root = resolved_root / ".trash" / str(uuid4())
    quarantined_root = operation_root / "images"
    moved: list[QuarantinedImageDirectory] = []
    try:
        validated: list[tuple[str, Path]] = []
        for case_id in case_ids:
            case_root = (resolved_root / case_id).resolve()
            if (
                case_root == resolved_root
                or not case_root.is_relative_to(resolved_root)
            ):
                raise ValueError(f"unsafe case image directory: {case_id}")
            validated.append((case_id, case_root))
        if any(case_root.exists() for _, case_root in validated):
            _write_deletion_manifest(operation_root, case_ids, "PREPARING")
        for case_id, case_root in validated:
            if not case_root.exists():
                continue
            quarantined_root.mkdir(parents=True, exist_ok=True)
            quarantined = quarantined_root / case_id
            case_root.replace(quarantined)
            moved.append((case_root, quarantined))
        if moved:
            _write_deletion_manifest(operation_root, case_ids, "QUARANTINED")
    except Exception:
        _restore_quarantined_images(operation_root, moved)
        raise
    return operation_root, moved


def _purge_quarantined_images(operation_root: Path) -> None:
    if not operation_root.exists():
        return
    shutil.rmtree(operation_root, ignore_errors=False)
    trash_root = operation_root.parent
    if trash_root.is_dir() and not any(trash_root.iterdir()):
        trash_root.rmdir()


def _recover_quarantined_images(
    image_root: Path,
    existing_case_ids: set[str],
) -> None:
    trash_root = image_root.resolve() / ".trash"
    if not trash_root.is_dir():
        return
    for operation_root in sorted(trash_root.iterdir()):
        if not operation_root.is_dir():
            continue
        case_ids = _read_deletion_case_ids(operation_root)
        quarantined_root = operation_root / "images"
        for case_id in case_ids:
            current_path = (
                quarantined_root / case_id
                if quarantined_root.is_dir()
                else operation_root / case_id
            )
            if not current_path.exists():
                continue
            if case_id in existing_case_ids:
                original_path = image_root.resolve() / case_id
                original_path.parent.mkdir(parents=True, exist_ok=True)
                current_path.replace(original_path)
            else:
                shutil.rmtree(current_path)
        _purge_quarantined_images(operation_root)


class _IdempotencyHeartbeat:
    def __init__(
        self,
        *,
        sessions,
        case_id: str,
        command: str,
        key: str,
        owner_id: str,
    ) -> None:
        self.sessions = sessions
        self.case_id = case_id
        self.command = command
        self.key = key
        self.owner_id = owner_id
        lease_seconds = CaseRepository.idempotency_lease.total_seconds()
        self.interval_seconds = max(0.01, min(30.0, lease_seconds / 3))
        self.stop = Event()
        self.error: Exception | None = None
        self.thread = Thread(
            target=self._run,
            name=f"idempotency-heartbeat-{owner_id}",
            daemon=True,
        )

    def _run(self) -> None:
        while not self.stop.wait(self.interval_seconds):
            try:
                with self.sessions() as session:
                    with session.begin():
                        renewed = CaseRepository(session).renew_idempotency(
                            self.case_id,
                            self.command,
                            self.key,
                            self.owner_id,
                        )
            except Exception as exc:
                self.error = exc
                return
            if not renewed:
                return

    def __enter__(self) -> "_IdempotencyHeartbeat":
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop.set()
        self.thread.join()
        if exc_type is None and self.error is not None:
            raise RuntimeError("idempotency heartbeat failed") from self.error


class CreateCaseRequest(BaseModel):
    instrument: str | None = None
    contract: str | None = None
    message: str | None = Field(default=None, max_length=4000)
    submission_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    strategy_id: str | None = None
    strategy_version: str | None = None
    agent_backend_id: str | None = None
    agent_model_id: str | None = None


class PositionRequest(BaseModel):
    direction: PositionDirection
    quantity: int = Field(ge=0)
    average_cost: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_position_state(self) -> "PositionRequest":
        if self.direction in {PositionDirection.FLAT, PositionDirection.UNKNOWN}:
            if self.quantity != 0:
                raise ValueError("flat or unknown position requires zero quantity")
            if self.average_cost is not None or self.stop_price is not None:
                raise ValueError("flat or unknown position cannot have cost or stop")
        elif self.quantity <= 0:
            raise ValueError("open position requires positive quantity")
        return self


class RiskRequest(BaseModel):
    account_risk_limit: float = Field(gt=0, le=1)
    proposed_risk: float = Field(ge=0, le=1)
    max_stop_distance_ratio: float = Field(default=0.03, gt=0, le=1)
    correlated_exposure_exceeded: bool = False


class ClarificationMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ConversationMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class StrategySelectionRequest(BaseModel):
    strategy_id: str
    version: str | None = None


class AgentBackendSelectionRequest(BaseModel):
    backend_id: str
    model_id: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1000)


LEGACY_STRATEGY_SUMMARY = {
    "strategy_id": "structure_confirmation",
    "version": "1.0.0",
    "display_name": "结构确认策略",
}

def create_app(
    database_url: str | None = None,
    storage_root: Path | None = None,
    vision_provider: VisionProvider | None = None,
    clarification_provider: ClarificationProvider | None = None,
    conversation_provider: ConversationProvider | None = None,
    agent_backend_registry: AgentBackendRegistry | None = None,
    strategy_registry: StrategyRegistry | None = None,
    market_data_resolver: MarketDataResolver | None = None,
    temporal_executor: TemporalExecutor | None = None,
    privacy_review_token: str | None = None,
    api_token: str | None = None,
    environment: str | None = None,
) -> FastAPI:
    database_url = (
        database_url
        or os.getenv("TRADING_AGENT_DATABASE_URL")
        or "sqlite+pysqlite:///./trading-agent.db"
    )
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    registry = strategy_registry or configured_strategy_registry()
    workflow = AnalysisWorkflow(strategy_registry=registry)
    image_root = (
        storage_root
        or Path(os.getenv("TRADING_AGENT_IMAGE_ROOT", "data/images"))
    )
    image_root.mkdir(parents=True, exist_ok=True)
    case_mutations = _CaseMutationCoordinator(image_root)
    deletion_cleanup = _DeletionCleanupRetrier(case_mutations)
    with case_mutations.locked():
        with sessions() as session:
            existing_case_ids = set(CaseRepository(session).case_ids())
        _recover_quarantined_images(image_root, existing_case_ids)
    settings = Settings()
    configured_registry = configured_agent_backend_registry(settings)
    if agent_backend_registry is not None:
        agents = agent_backend_registry
    elif any(
        item is not None
        for item in (
            vision_provider,
            clarification_provider,
            conversation_provider,
        )
    ):
        configured_manifests = configured_registry.manifests()

        def injected_runtime(backend_id: str, model_id: str) -> AgentRuntime:
            runtime = configured_registry.resolve(backend_id, model_id)
            if backend_id != "codex":
                return runtime
            return AgentRuntime(
                backend_id=backend_id,
                model_id=model_id,
                vision=vision_provider or runtime.vision,
                clarification=clarification_provider or runtime.clarification,
                conversation=conversation_provider or runtime.conversation,
            )

        agents = AgentBackendRegistry(
            manifests=configured_manifests,
            runtime_factory=injected_runtime,
        )
    else:
        agents = configured_registry
    resolver = market_data_resolver or configured_market_data_resolver()
    trusted_privacy_review_token = (
        privacy_review_token or os.getenv("TRADING_AGENT_PRIVACY_REVIEW_TOKEN")
    )
    temporal_address = os.getenv("TEMPORAL_ADDRESS")
    if temporal_executor is None and temporal_address:
        async def configured_temporal_executor(
            command: AnalysisCommand,
        ) -> dict[str, object]:
            client = await Client.connect(temporal_address)
            return await client.execute_workflow(
                DurableAnalysisWorkflow.run,
                command.model_dump(mode="json"),
                id=f"analysis-{command.case_id}-{command.idempotency_key}",
                task_queue=TASK_QUEUE,
                id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            )

        temporal_executor = configured_temporal_executor
    app = FastAPI(title="磐石交易AI")
    app.state.database_url = database_url
    app.state.sessions = sessions
    app.state.image_root = image_root
    app.state.case_mutations = case_mutations
    app.state.deletion_cleanup = deletion_cleanup
    default_runtime = agents.resolve("codex", settings.codex_model)
    app.state.vision_provider = default_runtime.vision
    app.state.market_data_resolver = resolver
    app.state.clarification_provider = default_runtime.clarification
    app.state.conversation_provider = default_runtime.conversation
    app.state.agent_backend_registry = agents
    app.state.strategy_registry = registry
    resolved_environment = (
        environment
        if environment is not None
        else os.getenv("TRADING_AGENT_ENVIRONMENT", "test")
    ).strip().lower()
    app.state.environment = resolved_environment
    resolved_api_token = api_token or os.getenv("TRADING_AGENT_API_TOKEN")

    @app.middleware("http")
    async def require_api_token(request, call_next):
        if request.url.path.startswith("/v1/") and not resolved_api_token:
            if resolved_environment != "test":
                return JSONResponse(
                    {"detail": "api authentication is not configured"},
                    status_code=503,
                )
        elif request.url.path.startswith("/v1/"):
            supplied = request.headers.get("Authorization", "")
            expected = f"Bearer {resolved_api_token}"
            if not secrets.compare_digest(supplied, expected):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    def require_key(value: str | None) -> str:
        if not value:
            raise HTTPException(400, "Idempotency-Key is required")
        return value

    def command_in_progress(exc: CommandInProgress) -> HTTPException:
        return HTTPException(409, f"command already in progress: {exc}")

    def default_strategy_summary() -> dict[str, str]:
        manifest = registry.default().manifest
        return {
            "strategy_id": manifest.strategy_id,
            "version": manifest.version,
            "display_name": manifest.display_name,
        }

    def project_case_strategy(state: dict) -> dict:
        if state.get("strategy"):
            return state
        return {
            **state,
            "strategy": dict(LEGACY_STRATEGY_SUMMARY),
        }

    def default_agent_backend_summary() -> dict[str, str]:
        backend = agents.manifest("codex")
        return {
            "backend_id": backend.backend_id,
            "model_id": backend.default_model_id,
            "display_name": backend.display_name,
        }

    def project_case_agent_backend(state: dict) -> dict:
        if state.get("agent_backend"):
            return state
        return {
            **state,
            "agent_backend": default_agent_backend_summary(),
        }

    def project_case(state: dict) -> dict:
        return project_case_agent_backend(project_case_strategy(state))

    def resolve_agent_runtime(
        backend_id: str | None,
        model_id: str | None,
    ) -> tuple[AgentRuntime, dict[str, str]]:
        selected_backend_id = backend_id or "codex"
        try:
            runtime = agents.resolve(selected_backend_id, model_id)
            backend = agents.manifest(runtime.backend_id)
        except AgentBackendUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return runtime, {
            "backend_id": runtime.backend_id,
            "model_id": runtime.model_id,
            "display_name": backend.display_name,
        }

    def resolve_case_runtime(
        state: dict,
    ) -> tuple[AgentRuntime, dict[str, str]]:
        selected = state.get("agent_backend")
        if not isinstance(selected, dict):
            selected = default_agent_backend_summary()
        return resolve_agent_runtime(
            str(selected.get("backend_id") or "codex"),
            (
                str(selected["model_id"])
                if selected.get("model_id")
                else None
            ),
        )

    @app.post("/v1/auth/login")
    def login(request: LoginRequest) -> dict:
        with sessions() as session:
            with session.begin():
                try:
                    return AuthService(session).login(
                        request.username,
                        request.password,
                    )
                except InvalidCredentials as exc:
                    raise HTTPException(
                        401,
                        "invalid username or password",
                    ) from exc

    @app.get("/v1/auth/session")
    def validate_auth_session(
        x_panshi_session: str | None = Header(default=None),
    ) -> dict:
        with sessions() as session:
            with session.begin():
                try:
                    return AuthService(session).validate_session(
                        x_panshi_session
                    )
                except InvalidSession as exc:
                    raise HTTPException(401, "invalid session") from exc

    @app.post("/v1/auth/logout")
    def logout(
        x_panshi_session: str | None = Header(default=None),
    ) -> dict[str, bool]:
        with sessions() as session:
            with session.begin():
                AuthService(session).logout(x_panshi_session)
        return {"ok": True}

    @app.get("/v1/strategies")
    def list_strategies() -> list[dict]:
        return [
            manifest.model_dump(mode="json")
            for manifest in registry.manifests()
            if manifest.status != "disabled"
        ]

    @app.get("/v1/agent-backends")
    def list_agent_backends() -> list[dict]:
        return [
            manifest.model_dump(mode="json")
            for manifest in agents.manifests()
        ]

    @app.get("/v1/cases")
    def list_cases() -> list[dict]:
        with sessions() as session:
            cases = CaseRepository(session).list_cases(limit=None)
        return [
            {
                **item,
                "strategy": (
                    item.get("strategy") or dict(LEGACY_STRATEGY_SUMMARY)
                ),
                "agent_backend": (
                    item.get("agent_backend")
                    or default_agent_backend_summary()
                ),
            }
            for item in cases
        ]

    @app.delete("/v1/cases")
    def delete_all_cases() -> dict[str, int]:
        with case_mutations.locked():
            with sessions() as session:
                case_ids = CaseRepository(session).case_ids()
            operation_root, moved = _quarantine_case_images(image_root, case_ids)
            try:
                with sessions() as session:
                    with session.begin():
                        deleted = CaseRepository(session).delete_all_cases()
            except Exception:
                _restore_quarantined_images(operation_root, moved)
                raise
            if operation_root.exists():
                try:
                    _write_deletion_manifest(
                        operation_root,
                        case_ids,
                        "DATABASE_COMMITTED",
                    )
                except OSError:
                    logger.exception("failed to update bulk deletion manifest")
                try:
                    _purge_quarantined_images(operation_root)
                except OSError:
                    logger.exception("deferred bulk deletion file cleanup")
                    deletion_cleanup.schedule(operation_root)
            return {"deleted": deleted}

    @app.post("/v1/cases", status_code=201)
    def create_case(
        request: CreateCaseRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        request_sha256 = sha256(
            json.dumps(
                request.model_dump(mode="json"),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        deterministic_case_id = (
            str(uuid5(NAMESPACE_URL, f"trading-agent:create-case:{idempotency_key}"))
            if idempotency_key
            else None
        )

        def replay_or_conflict(state: dict | None) -> dict | None:
            if state is None:
                return None
            if state.get("creation_request_sha256") != request_sha256:
                raise HTTPException(409, "idempotency key payload mismatch")
            return state

        if deterministic_case_id:
            with sessions() as session:
                replayed = replay_or_conflict(
                    CaseRepository(session).get_case(deterministic_case_id)
                )
            if replayed is not None:
                return replayed
        parsed = parse_user_message(request.message) if request.message else None
        try:
            selected_strategy = (
                registry.resolve(request.strategy_id, request.strategy_version)
                if request.strategy_id
                else registry.default()
            )
        except StrategyNotFound as exc:
            raise HTTPException(400, f"strategy not found: {exc}") from exc
        _, selected_agent_backend = resolve_agent_runtime(
            request.agent_backend_id,
            request.agent_model_id,
        )
        contract = request.contract or (parsed.get("contract") if parsed else None)
        position = parsed.get("position") if parsed else None
        risk = parsed.get("risk") if parsed else None
        if risk:
            risk = {key: value for key, value in risk.items() if value is not None}
        with case_mutations.locked():
            with sessions() as session:
                with session.begin():
                    repo = CaseRepository(session)
                    if deterministic_case_id:
                        replayed = replay_or_conflict(
                            repo.get_case(deterministic_case_id)
                        )
                        if replayed is not None:
                            return replayed
                    try:
                        with session.begin_nested():
                            return repo.create_case(
                                request.instrument,
                                contract,
                                case_id=deterministic_case_id,
                                creation_request_sha256=(
                                    request_sha256 if deterministic_case_id else None
                                ),
                                position=position,
                                risk=risk,
                                user_input=parsed,
                                strategy={
                                    "strategy_id": (
                                        selected_strategy.manifest.strategy_id
                                    ),
                                    "version": selected_strategy.manifest.version,
                                    "display_name": (
                                        selected_strategy.manifest.display_name
                                    ),
                                },
                                agent_backend=selected_agent_backend,
                            )
                    except IntegrityError:
                        replayed = replay_or_conflict(
                            repo.get_case(deterministic_case_id or "")
                        )
                        if replayed is None:
                            raise
                        return replayed

    @app.get("/v1/cases/{case_id}")
    def get_case(case_id: str) -> dict:
        with sessions() as session:
            state = CaseRepository(session).get_case(case_id)
            if state is None:
                raise HTTPException(404, "case not found")
            return project_case(state)

    @app.delete("/v1/cases/{case_id}")
    def delete_case(case_id: str) -> dict[str, int]:
        with case_mutations.locked():
            with sessions() as session:
                exists = CaseRepository(session).get_case(case_id) is not None
            case_ids = [case_id] if exists else []
            operation_root, moved = _quarantine_case_images(
                image_root,
                case_ids,
            )
            try:
                with sessions() as session:
                    with session.begin():
                        deleted = int(CaseRepository(session).delete_case(case_id))
            except Exception:
                _restore_quarantined_images(operation_root, moved)
                raise
            if operation_root.exists():
                try:
                    _write_deletion_manifest(
                        operation_root,
                        case_ids,
                        "DATABASE_COMMITTED",
                    )
                except OSError:
                    logger.exception(
                        "failed to update deletion manifest for case %s",
                        case_id,
                    )
                try:
                    _purge_quarantined_images(operation_root)
                except OSError:
                    logger.exception(
                        "deferred file cleanup for deleted case %s",
                        case_id,
                    )
                    deletion_cleanup.schedule(operation_root)
            return {"deleted": deleted}

    @app.get("/v1/cases/{case_id}/conversation")
    def get_conversation(case_id: str) -> dict:
        with sessions() as session:
            repo = CaseRepository(session)
            state = repo.get_case(case_id)
            if state is None:
                raise HTTPException(404, "case not found")
            analyses = repo.analyses(case_id)
        return {
            "case_id": case_id,
            "strategy": (
                state.get("strategy") or dict(LEGACY_STRATEGY_SUMMARY)
            ),
            "agent_backend": (
                state.get("agent_backend")
                or default_agent_backend_summary()
            ),
            "messages": state.get("messages", []),
            "current_analysis_id": (
                analyses[-1]["analysis_id"] if analyses else None
            ),
        }

    @app.post("/v1/cases/{case_id}/agent-backend")
    async def select_agent_backend(
        case_id: str,
        request: AgentBackendSelectionRequest,
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
        ),
    ) -> dict:
        key = require_key(idempotency_key)
        _, selected = resolve_agent_runtime(
            request.backend_id,
            request.model_id,
        )
        owner_id = str(uuid4())
        command = (
            "agent-backend-select:"
            f"{selected['backend_id']}:{selected['model_id']}"
        )
        try:
            with sessions() as session:
                with session.begin():
                    repo = CaseRepository(session)
                    state = repo.get_case(case_id)
                    if state is None:
                        raise HTTPException(404, "case not found")
                    try:
                        cached = repo.claim_idempotency(
                            case_id,
                            command,
                            key,
                            owner_id,
                        )
                    except CommandInProgress as exc:
                        raise command_in_progress(exc) from exc
                    if cached:
                        return cached
                    has_images = bool(state.get("images"))
            analysis_id = None
            staged_analysis: dict | None = None
            loaded_case_version: int | None = None
            if has_images:
                analysis_key = (
                    "agent-switch-analysis-"
                    + sha256(
                        (
                            f"{key}:{selected['backend_id']}:"
                            f"{selected['model_id']}"
                        ).encode("utf-8")
                    ).hexdigest()
                )
                with _IdempotencyHeartbeat(
                    sessions=sessions,
                    case_id=case_id,
                    command=command,
                    key=key,
                    owner_id=owner_id,
                ):
                    staged_analysis, loaded_case_version = (
                        await _prepare_agent_switch_analysis(
                        case_id,
                        analysis_key,
                        refresh_vision=True,
                        agent_backend_override=selected,
                    )
                    )
                analysis_id = staged_analysis["analysis_id"]
            with sessions() as session:
                with session.begin():
                    repo = CaseRepository(session)
                    state = repo.get_case(case_id)
                    if state is None:
                        raise HTTPException(404, "case not found")
                    if not repo.renew_idempotency(
                        case_id,
                        command,
                        key,
                        owner_id,
                    ):
                        raise CommandInProgress(f"{command}:{key}")
                    if staged_analysis is not None:
                        repo.save_analysis(
                            case_id,
                            staged_analysis,
                            expected_case_version=loaded_case_version,
                        )
                        state = repo.get_case(case_id)
                        if state is None:
                            raise HTTPException(404, "case not found")
                    payload = {
                        "agent_backend": selected,
                        "message": {
                            "message_id": str(uuid4()),
                            "role": "system",
                            "message_type": "AGENT_BACKEND_CHANGE",
                            "content": (
                                f"已切换至{selected['display_name']} "
                                f"({selected['model_id']})"
                            ),
                            "created_at": datetime.now(
                                timezone.utc
                            ).isoformat(),
                            "analysis_id": analysis_id,
                            "metadata": dict(selected),
                        },
                    }
                    state = repo._apply_event(
                        state,
                        "AGENT_BACKEND_SELECTED",
                        payload,
                    )
                    repo.update_case(
                        case_id,
                        state,
                        "AGENT_BACKEND_SELECTED",
                        payload,
                    )
                    result = {**selected, "analysis_id": analysis_id}
                    repo.complete_idempotency(
                        case_id,
                        command,
                        key,
                        owner_id,
                        result,
                    )
                    return result
        except Exception as exc:
            with sessions() as session:
                with session.begin():
                    CaseRepository(session).fail_idempotency(
                        case_id,
                        command,
                        key,
                        owner_id,
                    )
            if isinstance(exc, ProviderResponseError):
                raise HTTPException(502, str(exc)) from exc
            if isinstance(exc, ProviderUnavailable):
                raise HTTPException(503, str(exc)) from exc
            raise

    @app.post("/v1/cases/{case_id}/strategy")
    async def select_strategy(
        case_id: str,
        request: StrategySelectionRequest,
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
        ),
    ) -> dict:
        key = require_key(idempotency_key)
        owner_id = str(uuid4())
        try:
            plugin = registry.resolve(request.strategy_id, request.version)
        except StrategyNotFound as exc:
            raise HTTPException(400, f"strategy not found: {exc}") from exc
        selected = {
            "strategy_id": plugin.manifest.strategy_id,
            "version": plugin.manifest.version,
            "display_name": plugin.manifest.display_name,
        }
        try:
            with sessions() as session:
                with session.begin():
                    repo = CaseRepository(session)
                    state = repo.get_case(case_id)
                    if state is None:
                        raise HTTPException(404, "case not found")
                    try:
                        cached = repo.claim_idempotency(
                            case_id,
                            "strategy-select",
                            key,
                            owner_id,
                        )
                    except CommandInProgress as exc:
                        raise command_in_progress(exc) from exc
                    if cached:
                        return cached
                    current_strategy = state.get("strategy")
                    analyses = repo.analyses(case_id)
                    latest_manifest = (
                        analyses[-1].get("strategy_manifest", {})
                        if analyses
                        else {}
                    )
                    selection_already_recorded = any(
                        message.get("message_type") == "STRATEGY_CHANGE"
                        and message.get("metadata", {}).get("strategy_id")
                        == selected["strategy_id"]
                        and message.get("metadata", {}).get("strategy_version")
                        == selected["version"]
                        for message in state.get("messages", [])
                        if isinstance(message, dict)
                    )
                    if (
                        current_strategy != selected
                        or not selection_already_recorded
                    ):
                        event_payload = {
                            "strategy": selected,
                            "message": {
                                "message_id": str(uuid4()),
                                "role": "system",
                                "message_type": "STRATEGY_CHANGE",
                                "content": (
                                    f"已切换至{plugin.manifest.display_name} "
                                    f"v{plugin.manifest.version}"
                                ),
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "analysis_id": None,
                                "metadata": {
                                    "strategy_id": plugin.manifest.strategy_id,
                                    "strategy_version": plugin.manifest.version,
                                },
                            },
                        }
                        state = repo._apply_event(
                            state,
                            "STRATEGY_SELECTED",
                            event_payload,
                        )
                        repo.update_case(
                            case_id,
                            state,
                            "STRATEGY_SELECTED",
                            event_payload,
                        )
                    needs_analysis = bool(state.get("images")) and (
                        latest_manifest.get("strategy_id")
                        != selected["strategy_id"]
                        or latest_manifest.get("version") != selected["version"]
                    )
                    if not needs_analysis:
                        result = {**selected, "analysis_id": None}
                        repo.complete_idempotency(
                            case_id,
                            "strategy-select",
                            key,
                            owner_id,
                            result,
                        )
                        return result
            analysis_key = (
                "strategy-analysis-"
                + sha256(key.encode("utf-8")).hexdigest()
            )
            analysis = await analyze(
                case_id,
                analysis_key,
                refresh_vision=False,
            )
            result = {**selected, "analysis_id": analysis["analysis_id"]}
            with sessions() as session:
                with session.begin():
                    CaseRepository(session).complete_idempotency(
                        case_id,
                        "strategy-select",
                        key,
                        owner_id,
                        result,
                    )
            return result
        except Exception:
            with sessions() as session:
                with session.begin():
                    CaseRepository(session).fail_idempotency(
                        case_id,
                        "strategy-select",
                        key,
                        owner_id,
                    )
            raise

    @app.post("/v1/cases/{case_id}/messages")
    def post_conversation_message(
        case_id: str,
        request: ConversationMessageRequest,
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
        ),
    ) -> ConversationReply:
        key = require_key(idempotency_key)
        owner_id = str(uuid4())
        command = "conversation-message"
        with sessions() as session:
            with session.begin():
                repo = CaseRepository(session)
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                analyses = repo.analyses(case_id)
                if not analyses:
                    raise HTTPException(409, "analysis is required before follow-up")
                latest = analyses[-1]
                runtime, _ = resolve_case_runtime(state)
                try:
                    cached = repo.claim_idempotency(
                        case_id,
                        command,
                        key,
                        owner_id,
                    )
                except CommandInProgress as exc:
                    raise command_in_progress(exc) from exc
                if cached:
                    return ConversationReply.model_validate(cached)
        try:
            reply = ConversationService(runtime.conversation).reply(
                case_id=case_id,
                analysis=latest,
                message=request.message,
            )
            created_at = datetime.now(timezone.utc).isoformat()
            user_message = {
                "message_id": str(uuid4()),
                "role": "user",
                "message_type": "USER_MESSAGE",
                "content": request.message,
                "created_at": created_at,
                "analysis_id": latest["analysis_id"],
                "metadata": {},
            }
            assistant_message = {
                "message_id": str(uuid4()),
                "role": "assistant",
                "message_type": "STRATEGY_EXPLANATION",
                "content": reply.answer,
                "created_at": created_at,
                "analysis_id": reply.source_analysis_id,
                "metadata": {
                    "provider": reply.provider,
                    "model": reply.model,
                    "suggested_questions": reply.suggested_questions,
                },
            }
            with sessions() as session:
                with session.begin():
                    repo = CaseRepository(session)
                    state = repo.get_case(case_id)
                    if state is None:
                        raise HTTPException(404, "case not found")
                    for message in (user_message, assistant_message):
                        state = repo._apply_event(
                            state,
                            "CONVERSATION_MESSAGE_RECORDED",
                            message,
                        )
                        repo.update_case(
                            case_id,
                            state,
                            "CONVERSATION_MESSAGE_RECORDED",
                            message,
                        )
                    repo.complete_idempotency(
                        case_id,
                        command,
                        key,
                        owner_id,
                        reply.model_dump(mode="json"),
                    )
            return reply
        except Exception as exc:
            with sessions() as session:
                with session.begin():
                    CaseRepository(session).fail_idempotency(
                        case_id,
                        command,
                        key,
                        owner_id,
                    )
            if isinstance(exc, ProviderResponseError):
                raise HTTPException(502, str(exc)) from exc
            if isinstance(exc, ProviderUnavailable):
                raise HTTPException(503, str(exc)) from exc
            raise

    @app.post("/v1/cases/{case_id}/analysis-requests")
    def record_analysis_request(
        case_id: str,
        request: ConversationMessageRequest,
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
        ),
    ) -> dict:
        key = require_key(idempotency_key)
        owner_id = str(uuid4())
        command = "analysis-request"
        with sessions() as session:
            with session.begin():
                repo = CaseRepository(session)
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                try:
                    cached = repo.claim_idempotency(
                        case_id,
                        command,
                        key,
                        owner_id,
                    )
                except CommandInProgress as exc:
                    raise command_in_progress(exc) from exc
                if cached:
                    return cached
                message: dict[str, object] = {
                    "message_id": str(uuid4()),
                    "role": "user",
                    "message_type": "ANALYSIS_REQUEST",
                    "content": request.message,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "analysis_id": state.get("current_analysis_id"),
                    "metadata": {},
                }
                state = repo._apply_event(
                    state,
                    "CONVERSATION_MESSAGE_RECORDED",
                    message,
                )
                repo.update_case(
                    case_id,
                    state,
                    "CONVERSATION_MESSAGE_RECORDED",
                    message,
                )
                repo.complete_idempotency(
                    case_id,
                    command,
                    key,
                    owner_id,
                    message,
                )
                return message

    @app.post("/v1/cases/{case_id}/position")
    def update_position(
        case_id: str, request: PositionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        key = require_key(idempotency_key)
        owner_id = str(uuid4())
        with sessions() as session:
            with session.begin():
                repo = CaseRepository(session)
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                try:
                    cached = repo.claim_idempotency(
                        case_id, "position", key, owner_id
                    )
                except CommandInProgress as exc:
                    raise command_in_progress(exc) from exc
                if cached:
                    return cached
                state["position"] = request.model_dump(mode="json")
                repo.update_case(case_id, state, "POSITION_UPDATED", state["position"])
                repo.complete_idempotency(
                    case_id, "position", key, owner_id, state["position"]
                )
                return state["position"]

    @app.post("/v1/cases/{case_id}/risk")
    def update_risk(
        case_id: str,
        request: RiskRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        key = require_key(idempotency_key)
        owner_id = str(uuid4())
        with sessions() as session:
            with session.begin():
                repo = CaseRepository(session)
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                try:
                    cached = repo.claim_idempotency(case_id, "risk", key, owner_id)
                except CommandInProgress as exc:
                    raise command_in_progress(exc) from exc
                if cached:
                    return cached
                state["risk"] = request.model_dump(mode="json")
                repo.update_case(case_id, state, "RISK_UPDATED", state["risk"])
                repo.complete_idempotency(
                    case_id,
                    "risk",
                    key,
                    owner_id,
                    state["risk"],
                )
                return state["risk"]

    @app.post(
        "/v1/cases/{case_id}/images",
        status_code=201,
        response_model=None,
    )
    def upload_image(
        case_id: str, file: UploadFile = File(...),
        image_role: ImageRole = Form(default=ImageRole.AUXILIARY),
        role_confirmed: bool = Form(default=False),
        privacy_reviewed: bool = Form(default=False),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
        privacy_token: str | None = Header(default=None, alias="X-Privacy-Review-Token"),
    ) -> dict | JSONResponse:
        key = require_key(idempotency_key)
        owner_id = str(uuid4())
        content = file.file.read(MAX_IMAGE_BYTES + 1)
        try:
            suffix = validate_original_image_content(
                file.filename or "image.png",
                content,
            )
        except ValueError as exc:
            status_code = 413 if "maximum byte size" in str(exc) else 400
            raise HTTPException(status_code, str(exc)) from exc
        privacy = assess_upload_privacy(
            image_role=image_role,
            role_confirmed=role_confirmed,
            privacy_reviewed=privacy_reviewed,
            trusted_review=bool(
                trusted_privacy_review_token
                and privacy_token
                and secrets.compare_digest(
                    trusted_privacy_review_token,
                    privacy_token,
                )
            ),
        )
        content_sha256 = sha256(content).hexdigest()
        image_path: Path | None = None
        try:
            with case_mutations.locked():
                with sessions() as session:
                    with session.begin():
                        repo = CaseRepository(session)
                        state = repo.get_case(case_id)
                        if state is None:
                            raise HTTPException(404, "case not found")
                        try:
                            cached = repo.claim_idempotency(
                                case_id,
                                "image",
                                key,
                                owner_id,
                            )
                        except CommandInProgress as exc:
                            raise command_in_progress(exc) from exc
                        if cached:
                            return (
                                JSONResponse(cached, status_code=200)
                                if cached.get("duplicate") is True
                                else cached
                            )
                        duplicate = next(
                            (
                                item
                                for item in state.get("images", [])
                                if item.get("sha256") == content_sha256
                                and item.get("image_role") == image_role.value
                                and item.get("role_confirmed") is role_confirmed
                                and item.get("privacy_reviewed") is privacy_reviewed
                                and item.get("safe_for_model") is privacy.safe_for_model
                            ),
                            None,
                        )
                        if duplicate is not None:
                            result = {**duplicate, "duplicate": True}
                            repo.complete_idempotency(
                                case_id,
                                "image",
                                key,
                                owner_id,
                                result,
                            )
                            return JSONResponse(result, status_code=200)
                        image_id = str(uuid4())
                        case_root = image_root / case_id
                        case_root.mkdir(parents=True, exist_ok=True)
                        image_path = case_root / f"{image_id}{suffix}"
                        image_path.write_bytes(content)
                        result = {
                            "image_id": image_id, "filename": file.filename,
                            "sha256": content_sha256, "byte_size": len(content),
                            "path": str(image_path),
                            "image_role": image_role.value,
                            "role_confirmed": role_confirmed,
                            "privacy_reviewed": privacy_reviewed,
                            "privacy_review_trusted": privacy.safe_for_model,
                            "safe_for_model": privacy.safe_for_model,
                        }
                        state["image_ids"].append(result["image_id"])
                        state.setdefault("images", []).append(result)
                        repo.update_case(case_id, state, "IMAGE_UPLOADED", result)
                        repo.complete_idempotency(
                            case_id,
                            "image",
                            key,
                            owner_id,
                            result,
                        )
                        return result
        except Exception:
            if image_path is not None:
                image_path.unlink(missing_ok=True)
                if image_path.parent.is_dir() and not any(image_path.parent.iterdir()):
                    image_path.parent.rmdir()
            raise

    @app.get("/v1/cases/{case_id}/images/{image_id}")
    def get_original_image(case_id: str, image_id: str) -> FileResponse:
        with sessions() as session:
            state = CaseRepository(session).get_case(case_id)
            if state is None:
                raise HTTPException(404, "case not found")
            image = next(
                (
                    item
                    for item in state.get("images", [])
                    if item.get("image_id") == image_id
                ),
                None,
            )
        if image is None:
            raise HTTPException(404, "image not found")
        path = Path(str(image["path"])).resolve()
        case_root = (image_root / case_id).resolve()
        if not path.is_relative_to(case_root) or not path.is_file():
            raise HTTPException(404, "image not found")
        return FileResponse(path)

    async def _prepare_agent_switch_analysis(
        case_id: str,
        idempotency_key: str,
        *,
        refresh_vision: bool,
        agent_backend_override: dict[str, str],
    ) -> tuple[dict, int]:
        analysis_id = str(uuid4())
        with sessions() as session:
            repo = CaseRepository(session)
            state = repo.get_case(case_id)
            if state is None:
                raise HTTPException(404, "case not found")
            state = project_case_agent_backend(state)
            images = state.get("images", [])
            if not images:
                raise HTTPException(400, "analysis requires at least one image")
            state = {
                **state,
                "agent_backend": dict(agent_backend_override),
            }
            previous_analyses = repo.analyses(case_id)
            previous_analysis = previous_analyses[-1] if previous_analyses else None
            loaded_case_version = repo.case_version(case_id)
        if temporal_executor is not None:
            staged = await temporal_executor(
                AnalysisCommand(
                    case_id=case_id,
                    idempotency_key=idempotency_key,
                    storage_root=str(image_root.resolve()),
                    analysis_id=analysis_id,
                    refresh_vision=refresh_vision,
                    persist_result=False,
                    case_state=state,
                    case_version=loaded_case_version,
                    previous_analysis=previous_analysis,
                )
            )
            return dict(staged), loaded_case_version
        evidence_set = extract_case_evidence(
            case_state=state,
            images=images,
            provider=resolve_case_runtime(state)[0].vision,
            market_data_resolver=resolver,
            storage_root=image_root,
            previous_evidence_set=(
                previous_analysis.get("evidence_set", [])
                if previous_analysis and not refresh_vision
                else []
            ),
        )
        payload = build_analysis_payload(
            analysis_id=analysis_id,
            case_id=case_id,
            idempotency_key=idempotency_key,
            case_state=state,
            evidence_set=evidence_set,
            previous_analysis=previous_analysis,
            workflow=workflow,
        )
        return payload, loaded_case_version

    async def _analyze_case(
        case_id: str,
        idempotency_key: str,
        *,
        refresh_vision: bool,
        agent_backend_override: dict[str, str] | None = None,
    ) -> dict:
        key = require_key(idempotency_key)
        if temporal_executor is not None:
            with sessions() as session:
                repo = CaseRepository(session)
                cached = repo.idempotent_result(case_id, "analysis", key)
                if cached:
                    return cached
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                state = project_case_agent_backend(state)
                if not state.get("images"):
                    raise HTTPException(400, "analysis requires at least one image")
                if agent_backend_override is not None:
                    state = {
                        **state,
                        "agent_backend": dict(agent_backend_override),
                    }
                previous_analyses = repo.analyses(case_id)
                previous_analysis = (
                    previous_analyses[-1] if previous_analyses else None
                )
                loaded_case_version = repo.case_version(case_id)
            return await temporal_executor(
                AnalysisCommand(
                    case_id=case_id,
                    idempotency_key=key,
                    storage_root=str(image_root.resolve()),
                    refresh_vision=refresh_vision,
                    case_state=state,
                    case_version=loaded_case_version,
                    previous_analysis=previous_analysis,
                )
            )
        analysis_id = str(uuid4())
        with sessions() as session:
            with session.begin():
                repo = CaseRepository(session)
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                state = project_case_agent_backend(state)
                images = state.get("images", [])
                if not images:
                    raise HTTPException(400, "analysis requires at least one image")
                if agent_backend_override is not None:
                    state = {
                        **state,
                        "agent_backend": dict(agent_backend_override),
                    }
                try:
                    cached = repo.claim_idempotency(
                        case_id, "analysis", key, analysis_id
                    )
                except CommandInProgress as exc:
                    raise command_in_progress(exc) from exc
                if cached:
                    return cached
                previous_analyses = repo.analyses(case_id)
                previous_analysis = previous_analyses[-1] if previous_analyses else None
                loaded_case_version = repo.case_version(case_id)
        try:
            with sessions() as session:
                with session.begin():
                    if not CaseRepository(session).renew_idempotency(
                        case_id,
                        "analysis",
                        key,
                        analysis_id,
                    ):
                        raise CommandInProgress(f"analysis:{key}")
            with _IdempotencyHeartbeat(
                sessions=sessions,
                case_id=case_id,
                command="analysis",
                key=key,
                owner_id=analysis_id,
            ):
                evidence_set = extract_case_evidence(
                    case_state=state,
                    images=images,
                    provider=resolve_case_runtime(state)[0].vision,
                    market_data_resolver=resolver,
                    storage_root=image_root,
                    previous_evidence_set=(
                        previous_analysis.get("evidence_set", [])
                        if previous_analysis and not refresh_vision
                        else []
                    ),
                )
                payload = build_analysis_payload(
                    analysis_id=analysis_id,
                    case_id=case_id,
                    idempotency_key=key,
                    case_state=state,
                    evidence_set=evidence_set,
                    previous_analysis=previous_analysis,
                    workflow=workflow,
                )
            with sessions() as session:
                with session.begin():
                    repo = CaseRepository(session)
                    if not repo.renew_idempotency(
                        case_id,
                        "analysis",
                        key,
                        analysis_id,
                    ):
                        raise CommandInProgress(f"analysis:{key}")
                    repo.save_analysis(
                        case_id,
                        payload,
                        expected_case_version=loaded_case_version,
                    )
                    repo.complete_idempotency(
                        case_id, "analysis", key, analysis_id, payload
                    )
            return payload
        except Exception as exc:
            with sessions() as session:
                with session.begin():
                    CaseRepository(session).fail_idempotency(
                        case_id, "analysis", key, analysis_id
                    )
            if isinstance(exc, ProviderResponseError):
                raise HTTPException(502, str(exc)) from exc
            if isinstance(exc, ProviderUnavailable):
                raise HTTPException(503, str(exc)) from exc
            raise

    @app.post("/v1/cases/{case_id}/analysis")
    async def analyze(
        case_id: str,
        idempotency_key: str | None = Header(
            default=None,
            alias="Idempotency-Key",
        ),
        refresh_vision: bool = False,
    ) -> dict:
        return await _analyze_case(
            case_id,
            require_key(idempotency_key),
            refresh_vision=refresh_vision,
        )

    @app.get("/v1/cases/{case_id}/clarifications")
    def get_clarifications(case_id: str) -> dict:
        with sessions() as session:
            repo = CaseRepository(session)
            state = repo.get_case(case_id)
            if state is None:
                raise HTTPException(404, "case not found")
            analyses = repo.analyses(case_id)
        latest = analyses[-1] if analyses else None
        clarification_service = ClarificationService(
            resolve_case_runtime(state)[0].clarification,
            workflow=workflow,
        )
        return {
            "source_analysis_id": latest["analysis_id"] if latest else None,
            "questions": [
                question.model_dump(mode="json")
                for question in (
                    clarification_service.questions(latest) if latest else []
                )
            ],
            "history": state.get("clarifications", []),
        }

    @app.post("/v1/cases/{case_id}/clarifications")
    async def propose_clarification(
        case_id: str,
        request: ClarificationMessageRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        key = require_key(idempotency_key)
        clarification_id = str(uuid4())
        command = "clarification-message"
        with sessions() as session:
            with session.begin():
                repo = CaseRepository(session)
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                analyses = repo.analyses(case_id)
                if not analyses:
                    raise HTTPException(409, "analysis is required before clarification")
                latest = analyses[-1]
                clarification_service = ClarificationService(
                    resolve_case_runtime(state)[0].clarification,
                    workflow=workflow,
                )
                try:
                    cached = repo.claim_idempotency(
                        case_id,
                        command,
                        key,
                        clarification_id,
                    )
                except CommandInProgress as exc:
                    raise command_in_progress(exc) from exc
                if cached:
                    return cached
                questions = clarification_service.questions(latest)
        try:
            with _IdempotencyHeartbeat(
                sessions=sessions,
                case_id=case_id,
                command=command,
                key=key,
                owner_id=clarification_id,
            ):
                refreshed = await analyze(
                    case_id,
                    f"clarification-refresh-{clarification_id}",
                    refresh_vision=True,
                )
                refreshed_questions = clarification_service.questions(refreshed)
                if not refreshed_questions:
                    payload = {
                        "clarification_id": clarification_id,
                        "source_analysis_id": latest["analysis_id"],
                        "result_analysis_id": refreshed["analysis_id"],
                        "user_message": request.message,
                        "facts": [],
                        "resolved_question_ids": [
                            question.question_id for question in questions
                        ],
                        "unresolved_question_ids": [],
                        "interpretation": (
                            "系统已重新读取截图并刷新公开行情，"
                            "当前不再需要用户补充。"
                        ),
                        "provider": "automatic-evidence-refresh",
                        "model": "deterministic",
                        "status": "AUTO_RESOLVED",
                    }
                else:
                    proposal = clarification_service.interpret(
                        clarification_id=clarification_id,
                        case_id=case_id,
                        analysis=refreshed,
                        message=request.message,
                        questions=refreshed_questions,
                    )
                    payload = proposal.model_dump(mode="json")
            with sessions() as session:
                with session.begin():
                    repo = CaseRepository(session)
                    if not repo.renew_idempotency(
                        case_id,
                        command,
                        key,
                        clarification_id,
                    ):
                        raise CommandInProgress(f"{command}:{key}")
                    current = repo.analyses(case_id)
                    if (
                        not current
                        or current[-1]["analysis_id"] != refreshed["analysis_id"]
                    ):
                        raise HTTPException(
                            409,
                            "latest analysis changed; submit clarification again",
                        )
                    loaded_case_version = repo.case_version(case_id)
                    if payload["status"] == "AUTO_RESOLVED":
                        repo.append_event(
                            case_id,
                            "USER_ACTION_RECORDED",
                            {
                                "action": "CLARIFICATION_AUTO_REFRESHED",
                                **payload,
                            },
                            expected_version=loaded_case_version,
                        )
                    else:
                        repo.append_event(
                            case_id,
                            "CLARIFICATION_PROPOSED",
                            payload,
                            expected_version=loaded_case_version,
                        )
                    repo.complete_idempotency(
                        case_id,
                        command,
                        key,
                        clarification_id,
                        payload,
                    )
            return payload
        except Exception as exc:
            with sessions() as session:
                with session.begin():
                    CaseRepository(session).fail_idempotency(
                        case_id,
                        command,
                        key,
                        clarification_id,
                    )
            if isinstance(exc, ProviderResponseError):
                raise HTTPException(502, str(exc)) from exc
            if isinstance(exc, ProviderUnavailable):
                raise HTTPException(503, str(exc)) from exc
            if isinstance(exc, CaseVersionConflict):
                raise HTTPException(
                    409,
                    "latest analysis changed; submit clarification again",
                ) from exc
            raise

    @app.post(
        "/v1/cases/{case_id}/clarifications/{clarification_id}/confirm"
    )
    def confirm_clarification(
        case_id: str,
        clarification_id: str,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        key = require_key(idempotency_key)
        command = "clarification-confirm"
        analysis_id = str(uuid4())
        with sessions() as session:
            with session.begin():
                repo = CaseRepository(session)
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                proposal = next(
                    (
                        item
                        for item in state.get("clarifications", [])
                        if item.get("clarification_id") == clarification_id
                    ),
                    None,
                )
                if proposal is None:
                    raise HTTPException(404, "clarification not found")
                if proposal.get("status") == "CONFIRMED":
                    result_analysis_id = proposal.get("result_analysis_id")
                    existing = (
                        repo.analysis(case_id, str(result_analysis_id))
                        if result_analysis_id
                        else None
                    )
                    if existing is None:
                        raise HTTPException(
                            409,
                            "confirmed clarification result is unavailable",
                        )
                    return existing
                analyses = repo.analyses(case_id)
                if not analyses:
                    raise HTTPException(409, "analysis is required before confirmation")
                latest = analyses[-1]
                clarification_service = ClarificationService(
                    resolve_case_runtime(state)[0].clarification,
                    workflow=workflow,
                )
                if proposal.get("source_analysis_id") != latest["analysis_id"]:
                    raise HTTPException(
                        409,
                        "clarification does not belong to the latest analysis",
                    )
                try:
                    cached = repo.claim_idempotency(
                        case_id,
                        command,
                        key,
                        analysis_id,
                    )
                except CommandInProgress as exc:
                    raise command_in_progress(exc) from exc
                if cached:
                    return cached
                loaded_case_version = repo.case_version(case_id)
        try:
            payload = clarification_service.reevaluate(
                analysis_id=analysis_id,
                case_id=case_id,
                idempotency_key=key,
                case_state=state,
                previous_analysis=latest,
                proposal=proposal,
            )
            confirmed_at = datetime.now(timezone.utc).isoformat()
            confirmation_event = {
                "clarification_id": clarification_id,
                "confirmed_at": confirmed_at,
                "result_analysis_id": analysis_id,
                "facts": proposal.get("facts", []),
                "user_message": proposal.get("user_message"),
                "affected_blockers": list(
                    dict.fromkeys(
                        blocker
                        for fact in proposal.get("facts", [])
                        for blocker in fact.get("resolves_blockers", [])
                    )
                ),
            }
            with sessions() as session:
                with session.begin():
                    repo = CaseRepository(session)
                    if not repo.renew_idempotency(
                        case_id,
                        command,
                        key,
                        analysis_id,
                    ):
                        raise CommandInProgress(f"{command}:{key}")
                    current = repo.analyses(case_id)
                    if (
                        not current
                        or current[-1]["analysis_id"] != latest["analysis_id"]
                    ):
                        raise HTTPException(
                            409,
                            "clarification does not belong to the latest analysis",
                        )
                    repo.save_analysis(
                        case_id,
                        payload,
                        expected_case_version=loaded_case_version,
                    )
                    repo.append_event(
                        case_id,
                        "CLARIFICATION_CONFIRMED",
                        confirmation_event,
                        expected_version=loaded_case_version + 1,
                    )
                    repo.complete_idempotency(
                        case_id,
                        command,
                        key,
                        analysis_id,
                        payload,
                    )
            return payload
        except Exception as exc:
            with sessions() as session:
                with session.begin():
                    CaseRepository(session).fail_idempotency(
                        case_id,
                        command,
                        key,
                        analysis_id,
                    )
            if isinstance(exc, CaseVersionConflict):
                raise HTTPException(
                    409,
                    "clarification does not belong to the latest analysis",
                ) from exc
            raise

    @app.get("/v1/cases/{case_id}/analyses")
    def list_analyses(case_id: str) -> list[dict]:
        with sessions() as session:
            repo = CaseRepository(session)
            if repo.get_case(case_id) is None:
                raise HTTPException(404, "case not found")
            return repo.analyses(case_id)

    @app.get("/v1/cases/{case_id}/analyses/{analysis_id}")
    def get_analysis(case_id: str, analysis_id: str) -> dict:
        with sessions() as session:
            result = CaseRepository(session).analysis(case_id, analysis_id)
            if result is None:
                raise HTTPException(404, "analysis not found")
            return result

    @app.post("/v1/cases/{case_id}/actions")
    def record_action(case_id: str, payload: dict) -> dict:
        with sessions() as session:
            with session.begin():
                repo = CaseRepository(session)
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                repo.update_case(case_id, state, "USER_ACTION_RECORDED", payload)
                return payload

    @app.post("/v1/cases/{case_id}/close")
    def close_case(case_id: str) -> dict:
        with sessions() as session:
            with session.begin():
                repo = CaseRepository(session)
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                state["lifecycle"] = "CLOSED"
                repo.update_case(case_id, state, "CASE_CLOSED", {})
                return state

    return app


app = create_app(
    environment=os.getenv("TRADING_AGENT_ENVIRONMENT", "production"),
)
