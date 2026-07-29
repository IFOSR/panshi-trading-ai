from typing import Any
from uuid import uuid4

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from trading_agent.domain.enums import EvidenceUsage, MilestoneStatus
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategies.contracts import (
    StrategyInputSnapshot,
    StrategyManifest,
    StrategyRun,
    StrategySignal,
)
from trading_agent.strategies.registry import StrategyRegistry
from trading_agent.db.base import Base, build_engine, session_factory
from trading_agent.db.repositories import CaseRepository, CaseVersionConflict
from trading_agent.workflows.activities import (
    AnalysisActivities,
    AnalysisCommand,
    evaluate_strategy_stage,
    load_analysis_stage,
)
from trading_agent.workflows.worker import TASK_QUEUE, DurableAnalysisWorkflow


def test_temporal_worker_registers_named_workflow_and_queue() -> None:
    assert TASK_QUEUE == "trading-analysis"
    assert DurableAnalysisWorkflow.__name__ == "DurableAnalysisWorkflow"


def test_temporal_command_does_not_serialize_database_credentials() -> None:
    command = AnalysisCommand(
        case_id="case-1",
        idempotency_key="key-1",
        storage_root="/app/data/images",
    )

    assert "database" not in command.model_dump_json().lower()


def test_temporal_load_rejects_a_snapshot_after_case_state_changes(tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'snapshot.db'}"
    engine = build_engine(database_url)
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            state = repo.create_case("rb", "rb2610")
            case_id = state["case_id"]
            state["images"] = [{"image_id": "image-1", "path": "chart.png"}]
            state["image_ids"] = ["image-1"]
            repo.update_case(
                case_id,
                state,
                "IMAGE_UPLOADED",
                state["images"][0],
            )
            snapshot = repo.get_case(case_id)
            snapshot_version = repo.case_version(case_id)
            assert snapshot is not None
    with sessions() as session:
        with session.begin():
            repo = CaseRepository(session)
            state = repo.get_case(case_id)
            assert state is not None
            state["position"] = {"direction": "LONG", "quantity": 1}
            repo.update_case(
                case_id,
                state,
                "POSITION_UPDATED",
                state["position"],
            )

    command = AnalysisCommand(
        case_id=case_id,
        idempotency_key="analysis-1",
        storage_root=str(tmp_path),
        case_state=snapshot,
        case_version=snapshot_version,
        previous_analysis=None,
    )

    with pytest.raises(CaseVersionConflict):
        load_analysis_stage(
            command.model_dump(mode="json"),
            database_url=database_url,
        )


class TemporalThreeStepStrategy:
    manifest = StrategyManifest(
        strategy_id="temporal_three_step",
        display_name="Temporal 三步策略",
        version="3.1.0",
        status="test",
        entrypoint="tests:TemporalThreeStepStrategy",
        supported_markets=["CN_FUTURES"],
        supported_timeframes=["1d"],
        process_label="三步验证",
        risk_profile_id="china-futures-risk-v1",
    )

    def evaluate(self, snapshot: StrategyInputSnapshot) -> StrategyRun:
        return StrategyRun(
            manifest=self.manifest,
            milestones=[
                MilestoneResult(
                    number=number,
                    code=f"STEP_{number}",
                    status=MilestoneStatus.CONFIRMED,
                    result="CONFIRMED",
                )
                for number in range(1, 4)
            ],
            signal=StrategySignal(
                market_state="T+",
                setup_code="TEMPORAL_LONG",
                signal_stage="TRIGGERED",
                data_valid=True,
                price_confirmed=True,
                supporting_steps=[1, 2, 3],
                next_milestone="等待下一次策略状态更新",
            ),
        )


def test_temporal_evaluation_uses_the_case_pinned_strategy() -> None:
    registry = StrategyRegistry(default_strategy_id="temporal_three_step")
    registry.register(TemporalThreeStepStrategy())
    evidence = {
        "image_role": "STATE_DAILY",
        "contract": "rb2610",
        "timeframe": "1d",
        "cutoff_time": "2026-07-28T15:00:00+08:00",
        "last_bar_closed": True,
        "blocking_issues": [],
        "allowed_usage": EvidenceUsage.EXACT.value,
        "provider": "fixture",
        "model": "fixture",
        "prompt_version": "chart-evidence-v2",
        "image_sha256": "fixture",
    }

    result = evaluate_strategy_stage(
        {
            "command": {
                "case_id": "case-1",
                "idempotency_key": "analysis-1",
                "storage_root": "/tmp/images",
                "analysis_id": "analysis-1",
            },
            "case_state": {
                "contract": "rb2610",
                "position": {"direction": "FLAT", "quantity": 0},
                "strategy": {
                    "strategy_id": "temporal_three_step",
                    "version": "3.1.0",
                },
            },
            "evidence_set": [evidence],
            "previous_analysis": None,
        },
        strategy_registry=registry,
    )

    analysis = result["analysis"]
    assert analysis["strategy_manifest"]["strategy_id"] == "temporal_three_step"
    assert analysis["strategy_manifest"]["version"] == "3.1.0"
    assert len(analysis["milestones"]) == 4
    assert analysis["milestones"][-1]["code"] == "RISK_AND_ACTION"
    assert analysis["audit"]["strategy_id"] == "temporal_three_step"
    assert analysis["audit"]["strategy_version"] == "3.1.0"


@pytest.mark.asyncio
async def test_temporal_retries_only_multimodal_extraction_stage() -> None:
    calls: list[str] = []
    extraction_attempts = 0

    @activity.defn(name="load_analysis")
    async def load(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("load")
        return {"command": payload, "case_state": {"images": [{"path": "chart.png"}]}}

    @activity.defn(name="extract_evidence")
    async def extract(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal extraction_attempts
        calls.append("extract")
        extraction_attempts += 1
        if extraction_attempts == 1:
            raise RuntimeError("provider timeout")
        return {**payload, "evidence_set": [{"provider": "codex"}]}

    @activity.defn(name="renew_analysis")
    async def renew(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("renew")
        return payload

    @activity.defn(name="merge_market_data")
    async def merge(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("merge")
        return payload

    @activity.defn(name="evaluate_strategy")
    async def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("evaluate")
        return {**payload, "analysis": {"decision": {"action": "WAIT_FOR_DATA"}}}

    @activity.defn(name="persist_analysis")
    async def persist(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("persist")
        return payload["analysis"]

    @activity.defn(name="fail_analysis")
    async def fail(payload: dict[str, Any]) -> None:
        calls.append("fail")

    async with await WorkflowEnvironment.start_time_skipping() as environment:
        async with Worker(
            environment.client,
            task_queue=TASK_QUEUE,
            workflows=[DurableAnalysisWorkflow],
            activities=[load, renew, extract, merge, evaluate, persist, fail],
        ):
            result = await environment.client.execute_workflow(
                DurableAnalysisWorkflow.run,
                AnalysisCommand(
                    case_id="case-1",
                    idempotency_key="analysis-1",
                    storage_root="/tmp/images",
                    analysis_id=str(uuid4()),
                ).model_dump(mode="json"),
                id=f"test-{uuid4()}",
                task_queue=TASK_QUEUE,
            )

    assert result["decision"]["action"] == "WAIT_FOR_DATA"
    assert calls == [
        "load",
        "renew",
        "extract",
        "extract",
        "renew",
        "merge",
        "renew",
        "evaluate",
        "renew",
        "persist",
    ]


@pytest.mark.asyncio
async def test_temporal_releases_claim_after_extraction_retries_are_exhausted() -> None:
    calls: list[str] = []

    @activity.defn(name="load_analysis")
    async def load(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("load")
        return {"command": payload, "case_state": {"images": [{"path": "chart.png"}]}}

    @activity.defn(name="extract_evidence")
    async def extract(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("extract")
        raise RuntimeError("provider unavailable")

    @activity.defn(name="renew_analysis")
    async def renew(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("renew")
        return payload

    @activity.defn(name="merge_market_data")
    async def merge(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("merge")
        return payload

    @activity.defn(name="evaluate_strategy")
    async def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("evaluate")
        return payload

    @activity.defn(name="persist_analysis")
    async def persist(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("persist")
        return payload

    @activity.defn(name="fail_analysis")
    async def fail(payload: dict[str, Any]) -> None:
        calls.append("fail")

    async with await WorkflowEnvironment.start_time_skipping() as environment:
        async with Worker(
            environment.client,
            task_queue=TASK_QUEUE,
            workflows=[DurableAnalysisWorkflow],
            activities=[load, renew, extract, merge, evaluate, persist, fail],
        ):
            with pytest.raises(Exception):
                await environment.client.execute_workflow(
                    DurableAnalysisWorkflow.run,
                    AnalysisCommand(
                        case_id="case-1",
                        idempotency_key="analysis-1",
                        storage_root="/tmp/images",
                        analysis_id=str(uuid4()),
                    ).model_dump(mode="json"),
                    id=f"test-{uuid4()}",
                    task_queue=TASK_QUEUE,
                )

    assert calls == ["load", "renew", "extract", "extract", "fail"]


@pytest.mark.asyncio
async def test_registered_activity_set_uses_injected_market_data_resolver() -> None:
    class Resolver:
        called = False

        def resolve(self, case_state, evidence):
            self.called = True
            return None

    resolver = Resolver()
    activities = AnalysisActivities(market_data_resolver=resolver)
    evidence = {
        "image_role": "STATE_DAILY",
        "provider": "codex",
        "model": "gpt-5.6-sol",
        "prompt_version": "chart-evidence-v2",
        "image_sha256": "fixture",
    }

    await activities.merge_market_data(
        {
            "command": {
                "case_id": "case-1",
                "idempotency_key": "analysis-1",
                "storage_root": "/tmp/images",
            },
            "case_state": {"contract": "rb2610"},
            "evidence_set": [evidence],
        }
    )

    assert resolver.called is True
