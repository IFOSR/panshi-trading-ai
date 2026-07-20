from hashlib import sha256
import os
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from trading_agent.db.base import Base, build_engine, session_factory
from trading_agent.db.repositories import CaseRepository
from trading_agent.domain.enums import PositionDirection
from trading_agent.providers.base import VisionProvider, VisionRequest
from trading_agent.providers.codex import CodexVisionProvider
from trading_agent.providers.fallback import FallbackVisionProvider
from trading_agent.providers.kimi import KimiVisionProvider
from trading_agent.strategy.context import StrategyContext
from trading_agent.vision.privacy import PrivacyAssessment
from trading_agent.workflows.analysis import AnalysisWorkflow


class CreateCaseRequest(BaseModel):
    instrument: str | None = None
    contract: str | None = None


class PositionRequest(BaseModel):
    direction: PositionDirection
    quantity: int
    average_cost: float | None = None
    stop_price: float | None = None


def create_app(
    database_url: str | None = None,
    storage_root: Path | None = None,
    vision_provider: VisionProvider | None = None,
) -> FastAPI:
    database_url = (
        database_url
        or os.getenv("TRADING_AGENT_DATABASE_URL")
        or "sqlite+pysqlite:///./trading-agent.db"
    )
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    workflow = AnalysisWorkflow()
    image_root = storage_root or Path("data/images")
    image_root.mkdir(parents=True, exist_ok=True)
    provider = vision_provider or FallbackVisionProvider(
        primary=CodexVisionProvider(),
        fallback=KimiVisionProvider(),
    )
    app = FastAPI(title="China Futures Trading Agent")
    app.state.database_url = database_url

    def require_key(value: str | None) -> str:
        if not value:
            raise HTTPException(400, "Idempotency-Key is required")
        return value

    @app.post("/v1/cases", status_code=201)
    def create_case(request: CreateCaseRequest) -> dict:
        with sessions() as session:
            with session.begin():
                return CaseRepository(session).create_case(request.instrument, request.contract)

    @app.get("/v1/cases/{case_id}")
    def get_case(case_id: str) -> dict:
        with sessions() as session:
            state = CaseRepository(session).get_case(case_id)
            if state is None:
                raise HTTPException(404, "case not found")
            return state

    @app.post("/v1/cases/{case_id}/position")
    def update_position(
        case_id: str, request: PositionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        key = require_key(idempotency_key)
        with sessions() as session:
            with session.begin():
                repo = CaseRepository(session)
                cached = repo.idempotent_result(case_id, "position", key)
                if cached:
                    return cached
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                state["position"] = request.model_dump(mode="json")
                repo.update_case(case_id, state, "POSITION_UPDATED", state["position"])
                repo.save_idempotent(case_id, "position", key, state["position"])
                return state["position"]

    @app.post("/v1/cases/{case_id}/images", status_code=201)
    async def upload_image(
        case_id: str, file: UploadFile = File(...),
        safe_for_model: bool = Form(default=True),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        key = require_key(idempotency_key)
        content = await file.read()
        with sessions() as session:
            with session.begin():
                repo = CaseRepository(session)
                cached = repo.idempotent_result(case_id, "image", key)
                if cached:
                    return cached
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                image_id = str(uuid4())
                suffix = Path(file.filename or "image.png").suffix.lower()
                case_root = image_root / case_id
                case_root.mkdir(parents=True, exist_ok=True)
                image_path = case_root / f"{image_id}{suffix}"
                image_path.write_bytes(content)
                result = {
                    "image_id": image_id, "filename": file.filename,
                    "sha256": sha256(content).hexdigest(), "byte_size": len(content),
                    "path": str(image_path),
                    "safe_for_model": safe_for_model,
                }
                state["image_ids"].append(result["image_id"])
                state.setdefault("images", []).append(result)
                repo.update_case(case_id, state, "IMAGE_UPLOADED", result)
                repo.save_idempotent(case_id, "image", key, result)
                return result

    @app.post("/v1/cases/{case_id}/analysis")
    def analyze(
        case_id: str,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict:
        key = require_key(idempotency_key)
        with sessions() as session:
            with session.begin():
                repo = CaseRepository(session)
                cached = repo.idempotent_result(case_id, "analysis", key)
                if cached:
                    return cached
                state = repo.get_case(case_id)
                if state is None:
                    raise HTTPException(404, "case not found")
                images = state.get("images", [])
                if not images:
                    raise HTTPException(400, "analysis requires at least one image")
                latest = images[-1]
                request = VisionRequest(
                    prompt_version="chart-evidence-v1",
                    image_paths=[Path(latest["path"])],
                    storage_root=image_root,
                    privacy_assessment=PrivacyAssessment(
                        safe_for_model=bool(latest["safe_for_model"]),
                        contains_account_identifiers=not bool(latest["safe_for_model"]),
                    ),
                )
                evidence = provider.analyze(request)
                context = StrategyContext(
                    contract=evidence.contract or state.get("contract"),
                    timeframe=evidence.timeframe,
                    state_bar_closed=evidence.last_bar_closed,
                    position=state["position"]["direction"],
                    evidence_refs=[item.evidence_id for item in evidence.observations],
                )
                result = workflow.run(
                    case_id,
                    key,
                    context,
                    lambda: evidence.model_dump(mode="json"),
                )
                payload = {
                    "analysis_id": str(uuid4()),
                    "milestones": result.evaluation.model_dump(mode="json")["steps"],
                    "decision": result.decision.model_dump(mode="json"),
                    "rendered": result.rendered.model_dump(mode="json"),
                    "evidence": evidence.model_dump(mode="json"),
                }
                repo.save_analysis(case_id, payload)
                repo.save_idempotent(case_id, "analysis", key, payload)
                return payload

    @app.get("/v1/cases/{case_id}/analyses")
    def list_analyses(case_id: str) -> list[dict]:
        with sessions() as session:
            return CaseRepository(session).analyses(case_id)

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


app = create_app()
