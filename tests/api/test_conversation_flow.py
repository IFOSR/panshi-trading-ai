from fastapi.testclient import TestClient
from sqlalchemy import select

from trading_agent.api.app import create_app
from trading_agent.conversation.models import ConversationReply
from trading_agent.db.models import CaseEventRecord, CaseRecord
from trading_agent.db.repositories import CaseRepository
from trading_agent.domain.enums import EvidenceUsage, MilestoneStatus
from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategies.contracts import StrategyManifest
from trading_agent.strategies.contracts import (
    StrategyInputSnapshot,
    StrategyRun,
    StrategySignal,
)
from trading_agent.strategies.registry import StrategyRegistry
from trading_agent.strategies.structure_confirmation import (
    StructureConfirmationStrategy,
)


class FakeConversationProvider:
    def reply(self, request):
        return ConversationReply(
            source_analysis_id=request.source_analysis_id,
            answer="退出结论来自市场状态、策略方向和当前多仓冲突。",
            suggested_questions=["什么条件下可以重新入场？"],
            provider="fake",
            model="fixture",
        )


def client() -> TestClient:
    return TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            conversation_provider=FakeConversationProvider(),
        )
    )


def test_product_name_is_panshi_trading_ai() -> None:
    assert client().app.title == "磐石交易AI"


def test_lists_registered_strategies_for_the_selector() -> None:
    response = client().get("/v1/strategies")

    assert response.status_code == 200
    assert response.json() == [
        {
            "strategy_id": "structure_confirmation",
            "display_name": "结构确认策略",
            "version": "1.0.0",
            "status": "stable",
            "entrypoint": (
                "trading_agent.strategies.structure_confirmation:"
                "StructureConfirmationStrategy"
            ),
            "input_schema_version": "strategy-input-v1",
            "output_schema_version": "strategy-result-v1",
            "supported_markets": ["CN_FUTURES"],
            "supported_timeframes": ["1d", "60m"],
            "process_label": "八步结构确认",
            "risk_profile_id": "china-futures-risk-v1",
            "pricing": None,
            "performance_config": None,
        }
    ]


def test_new_case_pins_the_default_strategy_and_initial_message() -> None:
    response = client().post(
        "/v1/cases",
        json={"message": "请分析这张图。"},
    )

    assert response.status_code == 201
    state = response.json()
    assert state["strategy"] == {
        "strategy_id": "structure_confirmation",
        "version": "1.0.0",
        "display_name": "结构确认策略",
    }
    assert state["messages"][0]["role"] == "user"
    assert state["messages"][0]["content"] == "请分析这张图。"


def test_legacy_case_without_strategy_is_projected_to_the_default() -> None:
    api = client()
    state = api.post("/v1/cases", json={"contract": "cf2609"}).json()
    case_id = state["case_id"]
    with api.app.state.sessions() as session:
        with session.begin():
            event = session.scalar(
                select(CaseEventRecord).where(
                    CaseEventRecord.case_id == case_id,
                    CaseEventRecord.event_type == "CASE_CREATED",
                )
            )
            assert event is not None
            event.payload = {
                key: value
                for key, value in event.payload.items()
                if key != "strategy"
            }
            record = session.get(CaseRecord, case_id)
            assert record is not None
            record.state = {
                key: value
                for key, value in record.state.items()
                if key != "strategy"
            }

    conversation = api.get(f"/v1/cases/{case_id}/conversation")

    assert conversation.status_code == 200
    assert conversation.json()["strategy"] == {
        "strategy_id": "structure_confirmation",
        "version": "1.0.0",
        "display_name": "结构确认策略",
    }


def test_legacy_case_strategy_projection_does_not_drift_after_plugin_upgrade() -> None:
    class StructureConfirmationV2(StructureConfirmationStrategy):
        manifest = StrategyManifest(
            **{
                **StructureConfirmationStrategy.manifest.model_dump(),
                "version": "2.0.0",
            }
        )

    registry = StrategyRegistry(default_strategy_id="structure_confirmation")
    registry.register(StructureConfirmationStrategy())
    registry.register(StructureConfirmationV2())
    api = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            conversation_provider=FakeConversationProvider(),
            strategy_registry=registry,
        )
    )
    state = api.post("/v1/cases", json={"contract": "cf2609"}).json()
    case_id = state["case_id"]
    with api.app.state.sessions() as session:
        with session.begin():
            event = session.scalar(
                select(CaseEventRecord).where(
                    CaseEventRecord.case_id == case_id,
                    CaseEventRecord.event_type == "CASE_CREATED",
                )
            )
            assert event is not None
            event.payload = {
                key: value
                for key, value in event.payload.items()
                if key != "strategy"
            }
            record = session.get(CaseRecord, case_id)
            assert record is not None
            record.state = {
                key: value
                for key, value in record.state.items()
                if key != "strategy"
            }

    conversation = api.get(f"/v1/cases/{case_id}/conversation").json()

    assert conversation["strategy"]["version"] == "1.0.0"


def test_lists_recent_conversations_without_loading_analysis_payloads() -> None:
    api = client()
    first = api.post("/v1/cases", json={"contract": "rb2610"}).json()
    second = api.post("/v1/cases", json={"contract": "cf2609"}).json()

    response = api.get("/v1/cases")

    assert response.status_code == 200
    assert [item["case_id"] for item in response.json()] == [
        second["case_id"],
        first["case_id"],
    ]
    assert response.json()[0]["strategy"]["display_name"] == "结构确认策略"


def test_strategy_selection_is_idempotent_and_visible_in_conversation() -> None:
    api = client()
    case_id = api.post("/v1/cases", json={"contract": "cf2609"}).json()["case_id"]

    first = api.post(
        f"/v1/cases/{case_id}/strategy",
        headers={"Idempotency-Key": "strategy-1"},
        json={"strategy_id": "structure_confirmation", "version": "1.0.0"},
    )
    repeated = api.post(
        f"/v1/cases/{case_id}/strategy",
        headers={"Idempotency-Key": "strategy-1"},
        json={"strategy_id": "structure_confirmation", "version": "1.0.0"},
    )

    assert first.status_code == 200
    assert repeated.json() == first.json()
    conversation = api.get(f"/v1/cases/{case_id}/conversation").json()
    strategy_events = [
        message
        for message in conversation["messages"]
        if message["message_type"] == "STRATEGY_CHANGE"
    ]
    assert len(strategy_events) == 1
    assert strategy_events[0]["content"] == "已切换至结构确认策略 v1.0.0"


def test_strategy_switch_creates_a_new_analysis_version(tmp_path) -> None:
    class AlternateStrategy:
        manifest = StrategyManifest(
            strategy_id="alternate_structure",
            display_name="替代结构策略",
            version="1.0.0",
            status="test",
            entrypoint="tests:AlternateStrategy",
            supported_markets=["CN_FUTURES"],
            supported_timeframes=["1d"],
            process_label="三步结构确认",
            risk_profile_id="china-futures-risk-v1",
        )

        def evaluate(self, snapshot: StrategyInputSnapshot) -> StrategyRun:
            return StrategyRun(
                manifest=self.manifest,
                milestones=[
                    MilestoneResult(
                        number=number,
                        code=f"ALT_{number}",
                        title=f"替代步骤 {number}",
                        status=MilestoneStatus.CONFIRMED,
                        result="CONFIRMED",
                    )
                    for number in range(1, 4)
                ],
                signal=StrategySignal(
                    market_state="T+",
                    setup_code="ALT_LONG",
                    signal_stage="TRIGGERED",
                    data_valid=True,
                    price_confirmed=True,
                    supporting_steps=[1, 2, 3],
                ),
            )

    class VisionProvider:
        def analyze(self, request):
            return ScreenshotEvidence(
                image_role="STATE_DAILY",
                contract="cf2609",
                timeframe="1d",
                cutoff_time="2026-07-28T15:00:00+08:00",
                last_bar_closed=True,
                blocking_issues=[],
                allowed_usage=EvidenceUsage.EXACT,
                provider="fixture",
                model="fixture",
                prompt_version=request.prompt_version,
                image_sha256="fixture",
            )

    registry = StrategyRegistry(default_strategy_id="structure_confirmation")
    registry.register(StructureConfirmationStrategy())
    registry.register(AlternateStrategy())
    api = TestClient(
        create_app(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'switch.db'}",
            storage_root=tmp_path / "images",
            vision_provider=VisionProvider(),
            conversation_provider=FakeConversationProvider(),
            strategy_registry=registry,
            privacy_review_token="trusted-review",
        )
    )
    case_id = api.post("/v1/cases", json={"contract": "cf2609"}).json()[
        "case_id"
    ]
    api.post(
        f"/v1/cases/{case_id}/images",
        headers={
            "Idempotency-Key": "image-1",
            "X-Privacy-Review-Token": "trusted-review",
        },
        data={
            "image_role": "STATE_DAILY",
            "role_confirmed": "true",
            "privacy_reviewed": "true",
        },
        files={"file": ("chart.png", b"\x89PNG\r\n\x1a\nfixture", "image/png")},
    ).raise_for_status()
    api.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis-1"},
    ).raise_for_status()

    switched = api.post(
        f"/v1/cases/{case_id}/strategy",
        headers={"Idempotency-Key": "strategy-alternate"},
        json={"strategy_id": "alternate_structure", "version": "1.0.0"},
    )

    assert switched.status_code == 200
    payload = switched.json()
    assert payload["analysis_id"]
    analyses = api.get(f"/v1/cases/{case_id}/analyses").json()
    assert len(analyses) == 2
    assert analyses[-1]["analysis_id"] == payload["analysis_id"]
    assert analyses[-1]["strategy_manifest"]["strategy_id"] == (
        "alternate_structure"
    )
    conversation = api.get(f"/v1/cases/{case_id}/conversation").json()
    assert conversation["current_analysis_id"] == payload["analysis_id"]


def test_explanation_follow_up_is_bound_to_the_latest_analysis() -> None:
    api = client()
    state = api.post(
        "/v1/cases",
        json={"contract": "cf2609", "message": "为什么要退出？"},
    ).json()
    case_id = state["case_id"]
    sessions = api.app.state.sessions
    analysis = {
        "analysis_id": "analysis-1",
        "created_at": "2026-07-28T16:00:00+08:00",
        "strategy_manifest": {
            "strategy_id": "structure_confirmation",
            "display_name": "结构确认策略",
            "version": "1.0.0",
            "status": "stable",
            "entrypoint": "fixture",
            "input_schema_version": "strategy-input-v1",
            "output_schema_version": "strategy-result-v1",
            "supported_markets": ["CN_FUTURES"],
            "supported_timeframes": ["1d", "60m"],
            "process_label": "八步结构确认",
            "risk_profile_id": "china-futures-risk-v1",
        },
        "milestones": [],
        "decision": {
            "action": "EXIT",
            "market_state": "T-",
            "position_scope": "LONG",
            "supporting_steps": [1],
            "blocking_steps": [],
            "reason_codes": [],
            "evidence_refs": [],
            "strategy": "TREND_PULLBACK_SHORT",
            "signal_stage": "NOT_TRIGGERED",
            "next_milestone": "等待下一次策略状态更新",
            "upgrade_conditions": [],
            "invalidation_conditions": [],
            "missing_information": [],
        },
        "rendered": {
            "action": "EXIT",
            "summary": "退出持仓",
            "supporting_steps": [1],
            "blocking_steps": [],
            "upgrade_conditions": [],
            "invalidation_conditions": [],
            "next_milestone": "等待下一次策略状态更新",
            "data_limitations": [],
            "position_branches": [],
        },
        "evidence": {},
        "evidence_set": [],
    }
    with sessions() as session:
        with session.begin():
            CaseRepository(session).save_analysis(case_id, analysis)

    response = api.post(
        f"/v1/cases/{case_id}/messages",
        headers={"Idempotency-Key": "follow-up-1"},
        json={"message": "为什么不是继续持有？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_analysis_id"] == "analysis-1"
    assert payload["answer"].startswith("退出结论")
    analyses = api.get(f"/v1/cases/{case_id}/analyses").json()
    assert analyses[-1]["decision"]["action"] == "EXIT"
    conversation = api.get(f"/v1/cases/{case_id}/conversation").json()
    assert conversation["messages"][-2]["content"] == "为什么不是继续持有？"
    assert conversation["messages"][-1]["role"] == "assistant"

    repeated = api.post(
        f"/v1/cases/{case_id}/messages",
        headers={"Idempotency-Key": "follow-up-1"},
        json={"message": "为什么不是继续持有？"},
    )

    assert repeated.json() == payload
    replayed_conversation = api.get(
        f"/v1/cases/{case_id}/conversation"
    ).json()
    assert len(replayed_conversation["messages"]) == len(
        conversation["messages"]
    )


def test_analysis_request_is_idempotently_recorded_in_the_conversation() -> None:
    api = client()
    case_id = api.post(
        "/v1/cases",
        json={"contract": "cf2609", "message": "初始分析。"},
    ).json()["case_id"]

    first = api.post(
        f"/v1/cases/{case_id}/analysis-requests",
        headers={"Idempotency-Key": "refresh-request-1"},
        json={"message": "刷新公开行情并重新分析。"},
    )
    repeated = api.post(
        f"/v1/cases/{case_id}/analysis-requests",
        headers={"Idempotency-Key": "refresh-request-1"},
        json={"message": "刷新公开行情并重新分析。"},
    )

    assert first.status_code == 200
    assert repeated.json() == first.json()
    conversation = api.get(f"/v1/cases/{case_id}/conversation").json()
    matching = [
        item
        for item in conversation["messages"]
        if item["content"] == "刷新公开行情并重新分析。"
    ]
    assert len(matching) == 1
    assert matching[0]["message_type"] == "ANALYSIS_REQUEST"
