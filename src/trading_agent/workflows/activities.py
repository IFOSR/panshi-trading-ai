import os
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel

from trading_agent.db.base import build_engine, session_factory
from trading_agent.db.repositories import CaseRepository
from trading_agent.providers.base import VisionProvider, VisionRequest
from trading_agent.providers.codex import CodexVisionProvider
from trading_agent.providers.fallback import FallbackVisionProvider
from trading_agent.providers.kimi import KimiVisionProvider
from trading_agent.strategy.context import StrategyContext
from trading_agent.vision.privacy import PrivacyAssessment
from trading_agent.workflows.analysis import AnalysisWorkflow


class AnalysisCommand(BaseModel):
    case_id: str
    idempotency_key: str
    storage_root: str


def execute_analysis_command(
    command: AnalysisCommand,
    *,
    database_url: str | None = None,
    provider: VisionProvider | None = None,
) -> dict[str, object]:
    resolved_database_url = (
        database_url
        or os.getenv("TRADING_AGENT_DATABASE_URL")
        or "sqlite+pysqlite:///./trading-agent.db"
    )
    engine = build_engine(resolved_database_url)
    sessions = session_factory(engine)
    vision_provider = provider or FallbackVisionProvider(
        primary=CodexVisionProvider(),
        fallback=KimiVisionProvider(),
    )
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            cached = repo.idempotent_result(
                command.case_id, "analysis", command.idempotency_key
            )
            if cached:
                return cached
            state = repo.get_case(command.case_id)
            if state is None:
                raise ValueError("case not found")
            images = state.get("images", [])
            if not images:
                raise ValueError("analysis requires at least one image")
            latest = images[-1]
            evidence = vision_provider.analyze(
                VisionRequest(
                    prompt_version="chart-evidence-v1",
                    image_paths=[Path(latest["path"])],
                    storage_root=Path(command.storage_root),
                    privacy_assessment=PrivacyAssessment(
                        safe_for_model=bool(latest["safe_for_model"]),
                        contains_account_identifiers=not bool(latest["safe_for_model"]),
                    ),
                )
            )
            context = StrategyContext(
                contract=evidence.contract or state.get("contract"),
                timeframe=evidence.timeframe,
                state_bar_closed=evidence.last_bar_closed,
                position=state["position"]["direction"],
                evidence_refs=[item.evidence_id for item in evidence.observations],
            )
            result = AnalysisWorkflow().run(
                command.case_id,
                command.idempotency_key,
                context,
                lambda: evidence.model_dump(mode="json"),
            )
            payload: dict[str, object] = {
                "analysis_id": str(uuid4()),
                "milestones": result.evaluation.model_dump(mode="json")["steps"],
                "decision": result.decision.model_dump(mode="json"),
                "rendered": result.rendered.model_dump(mode="json"),
                "evidence": evidence.model_dump(mode="json"),
            }
            repo.save_analysis(command.case_id, payload)
            repo.save_idempotent(
                command.case_id,
                "analysis",
                command.idempotency_key,
                payload,
            )
            return payload
