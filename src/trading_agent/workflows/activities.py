import asyncio
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
from temporalio import activity

from trading_agent.db.base import build_engine, session_factory
from trading_agent.db.repositories import (
    CaseRepository,
    CaseVersionConflict,
    CommandInProgress,
)
from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.market.resolver import MarketDataResolver, NullMarketDataResolver
from trading_agent.providers.base import VisionProvider
from trading_agent.providers.factory import configured_fallback_provider
from trading_agent.services.analysis import build_analysis_payload
from trading_agent.services.evidence_pipeline import (
    extract_original_images,
    merge_case_market_data,
)
from trading_agent.strategies.registry import (
    StrategyRegistry,
    configured_strategy_registry,
)
from trading_agent.workflows.analysis import AnalysisWorkflow


class AnalysisCommand(BaseModel):
    case_id: str
    idempotency_key: str
    storage_root: str
    analysis_id: str = Field(default_factory=lambda: str(uuid4()))
    refresh_vision: bool = False
    case_state: dict[str, Any] | None = None
    case_version: int | None = None
    previous_analysis: dict[str, Any] | None = None


def _database_url(database_url: str | None = None) -> str:
    return (
        database_url
        or os.getenv("TRADING_AGENT_DATABASE_URL")
        or "sqlite+pysqlite:///./trading-agent.db"
    )


def _provider(provider: VisionProvider | None = None) -> VisionProvider:
    if provider is not None:
        return provider
    return configured_fallback_provider()


def load_analysis_stage(
    payload: dict[str, Any],
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    command = AnalysisCommand.model_validate(payload)
    sessions = session_factory(build_engine(_database_url(database_url)))
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            cached = repo.idempotent_result(
                command.case_id,
                "analysis",
                command.idempotency_key,
            )
            if cached:
                return {
                    "command": command.model_dump(mode="json"),
                    "cached_result": cached,
                }
            state: dict[str, Any]
            previous: dict[str, Any] | None
            if command.case_state is not None:
                if repo.get_case(command.case_id) is None:
                    raise ValueError("case not found")
                if (
                    command.case_version is None
                    or repo.case_version(command.case_id) != command.case_version
                ):
                    raise CaseVersionConflict(
                        f"case {command.case_id} changed after analysis submission"
                    )
                state = command.case_state
                previous = command.previous_analysis
                case_version = command.case_version
            else:
                loaded_state = repo.get_case(command.case_id)
                if loaded_state is None:
                    raise ValueError("case not found")
                state = loaded_state
                previous_analyses = repo.analyses(command.case_id)
                previous = previous_analyses[-1] if previous_analyses else None
                case_version = repo.case_version(command.case_id)
            if not state.get("images"):
                raise ValueError("analysis requires at least one image")
            cached = repo.claim_idempotency(
                command.case_id,
                "analysis",
                command.idempotency_key,
                command.analysis_id,
            )
            if cached:
                return {
                    "command": command.model_dump(mode="json"),
                    "cached_result": cached,
                }
            return {
                "command": command.model_dump(mode="json"),
                "case_state": state,
                "case_version": case_version,
                "previous_analysis": previous,
            }


def extract_evidence_stage(
    payload: dict[str, Any],
    *,
    provider: VisionProvider | None = None,
) -> dict[str, Any]:
    if payload.get("cached_result"):
        return payload
    command = AnalysisCommand.model_validate(payload["command"])
    state = dict(payload["case_state"])
    evidence_set = extract_original_images(
        images=state["images"],
        provider=_provider(provider),
        storage_root=Path(command.storage_root),
        previous_evidence_set=(
            payload.get("previous_analysis", {}).get("evidence_set", [])
            if payload.get("previous_analysis") and not command.refresh_vision
            else []
        ),
    )
    return {
        **payload,
        "evidence_set": [
            evidence.model_dump(mode="json") for evidence in evidence_set
        ],
    }


def renew_analysis_stage(
    payload: dict[str, Any],
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    if payload.get("cached_result"):
        return payload
    command = AnalysisCommand.model_validate(payload["command"])
    sessions = session_factory(build_engine(_database_url(database_url)))
    with sessions() as session:
        with session.begin():
            renewed = CaseRepository(session).renew_idempotency(
                command.case_id,
                "analysis",
                command.idempotency_key,
                command.analysis_id,
            )
    if not renewed:
        raise CommandInProgress(
            f"analysis:{command.idempotency_key} lease is no longer owned"
        )
    return payload


def merge_market_stage(
    payload: dict[str, Any],
    *,
    market_data_resolver: MarketDataResolver | None = None,
) -> dict[str, Any]:
    if payload.get("cached_result"):
        return payload
    state = dict(payload["case_state"])
    evidence_set = [
        ScreenshotEvidence.model_validate(item) for item in payload["evidence_set"]
    ]
    merged = merge_case_market_data(
        case_state=state,
        evidence_set=evidence_set,
        market_data_resolver=market_data_resolver or NullMarketDataResolver(),
    )
    return {
        **payload,
        "evidence_set": [
            evidence.model_dump(mode="json") for evidence in merged
        ],
    }


def evaluate_strategy_stage(
    payload: dict[str, Any],
    *,
    strategy_registry: StrategyRegistry | None = None,
) -> dict[str, Any]:
    if payload.get("cached_result"):
        return payload
    command = AnalysisCommand.model_validate(payload["command"])
    state = dict(payload["case_state"])
    evidence_set = [
        ScreenshotEvidence.model_validate(item) for item in payload["evidence_set"]
    ]
    analysis = build_analysis_payload(
        analysis_id=command.analysis_id,
        case_id=command.case_id,
        idempotency_key=command.idempotency_key,
        case_state=state,
        evidence_set=evidence_set,
        previous_analysis=payload.get("previous_analysis"),
        workflow=AnalysisWorkflow(
            max_provider_attempts=1,
            strategy_registry=(
                strategy_registry or configured_strategy_registry()
            ),
        ),
    )
    return {**payload, "analysis": analysis}


def persist_analysis_stage(
    payload: dict[str, Any],
    *,
    database_url: str | None = None,
) -> dict[str, Any]:
    if cached := payload.get("cached_result"):
        return dict(cached)
    command = AnalysisCommand.model_validate(payload["command"])
    analysis = dict(payload["analysis"])
    sessions = session_factory(build_engine(_database_url(database_url)))
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            cached = repo.idempotent_result(
                command.case_id,
                "analysis",
                command.idempotency_key,
            )
            if cached:
                return cached
            repo.save_analysis(
                command.case_id,
                analysis,
                expected_case_version=int(payload["case_version"]),
            )
            repo.complete_idempotency(
                command.case_id,
                "analysis",
                command.idempotency_key,
                command.analysis_id,
                analysis,
            )
    return analysis


def fail_analysis_stage(
    payload: dict[str, Any],
    *,
    database_url: str | None = None,
) -> None:
    raw_command = payload.get("command", payload)
    command = AnalysisCommand.model_validate(raw_command)
    sessions = session_factory(build_engine(_database_url(database_url)))
    with sessions() as session:
        with session.begin():
            CaseRepository(session).fail_idempotency(
                command.case_id,
                "analysis",
                command.idempotency_key,
                command.analysis_id,
            )


def execute_analysis_command(
    command: AnalysisCommand,
    *,
    database_url: str | None = None,
    provider: VisionProvider | None = None,
    market_data_resolver: MarketDataResolver | None = None,
    strategy_registry: StrategyRegistry | None = None,
) -> dict[str, Any]:
    loaded = load_analysis_stage(command.model_dump(mode="json"), database_url=database_url)
    try:
        extracted = extract_evidence_stage(loaded, provider=provider)
        merged = merge_market_stage(extracted, market_data_resolver=market_data_resolver)
        evaluated = evaluate_strategy_stage(
            merged,
            strategy_registry=strategy_registry,
        )
        return persist_analysis_stage(evaluated, database_url=database_url)
    except Exception:
        fail_analysis_stage(loaded, database_url=database_url)
        raise


class AnalysisActivities:
    def __init__(
        self,
        *,
        database_url: str | None = None,
        provider: VisionProvider | None = None,
        market_data_resolver: MarketDataResolver | None = None,
        strategy_registry: StrategyRegistry | None = None,
    ) -> None:
        self.database_url = database_url
        self.provider = provider
        self.market_data_resolver = market_data_resolver or NullMarketDataResolver()
        self.strategy_registry = (
            strategy_registry or configured_strategy_registry()
        )

    @activity.defn(name="load_analysis")
    async def load_analysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(
            load_analysis_stage,
            payload,
            database_url=self.database_url,
        )

    @activity.defn(name="extract_evidence")
    async def extract_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(
            extract_evidence_stage,
            payload,
            provider=self.provider,
        )

    @activity.defn(name="renew_analysis")
    async def renew_analysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(
            renew_analysis_stage,
            payload,
            database_url=self.database_url,
        )

    @activity.defn(name="merge_market_data")
    async def merge_market_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(
            merge_market_stage,
            payload,
            market_data_resolver=self.market_data_resolver,
        )

    @activity.defn(name="evaluate_strategy")
    async def evaluate_strategy(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(
            evaluate_strategy_stage,
            payload,
            strategy_registry=self.strategy_registry,
        )

    @activity.defn(name="persist_analysis")
    async def persist_analysis(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(
            persist_analysis_stage,
            payload,
            database_url=self.database_url,
        )

    @activity.defn(name="fail_analysis")
    async def fail_analysis(self, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(
            fail_analysis_stage,
            payload,
            database_url=self.database_url,
        )
