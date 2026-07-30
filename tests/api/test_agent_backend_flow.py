from fastapi.testclient import TestClient

from trading_agent.agents.models import (
    AgentBackendManifest,
    AgentModelManifest,
    AgentRuntime,
)
from trading_agent.agents.registry import AgentBackendRegistry
from trading_agent.api.app import create_app
from trading_agent.conversation.models import ConversationReply
from trading_agent.db.repositories import CaseRepository
from trading_agent.domain.enums import EvidenceUsage
from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.providers.base import ProviderUnavailable


class Provider:
    def analyze(self, request):
        raise AssertionError("vision is not needed")

    def interpret(self, request):
        raise AssertionError("clarification is not needed")

    def reply(self, request):
        raise AssertionError("conversation is not needed")


def registry() -> AgentBackendRegistry:
    capabilities = ["vision", "clarification", "conversation"]
    manifests = [
        AgentBackendManifest(
            backend_id="codex",
            display_name="Codex",
            default_model_id="gpt-5.6-sol",
            capabilities=capabilities,
            available=True,
            models=[
                AgentModelManifest(
                    model_id="gpt-5.6-sol",
                    display_name="GPT-5.6",
                    capabilities=capabilities,
                    available=True,
                )
            ],
        ),
        AgentBackendManifest(
            backend_id="kimi",
            display_name="Kimi Code",
            default_model_id="kimi-k3",
            capabilities=capabilities,
            available=True,
            models=[
                AgentModelManifest(
                    model_id="kimi-k3",
                    display_name="Kimi 3",
                    capabilities=capabilities,
                    available=True,
                ),
                AgentModelManifest(
                    model_id="kimi-code/kimi-for-coding",
                    display_name="Kimi for Coding",
                    capabilities=capabilities,
                    available=False,
                    unavailable_reason="缺少 image_in",
                ),
            ],
        ),
    ]

    def make_runtime(backend_id: str, model_id: str) -> AgentRuntime:
        provider = Provider()
        return AgentRuntime(
            backend_id=backend_id,
            model_id=model_id,
            vision=provider,
            clarification=provider,
            conversation=provider,
        )

    return AgentBackendRegistry(
        manifests=manifests,
        runtime_factory=make_runtime,
    )


def client() -> TestClient:
    return TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            agent_backend_registry=registry(),
        )
    )


class RoutedProvider:
    def __init__(
        self,
        backend_id: str,
        calls: list[str],
        *,
        fail_vision: bool = False,
    ) -> None:
        self.backend_id = backend_id
        self.calls = calls
        self.fail_vision = fail_vision

    def analyze(self, request):
        self.calls.append(f"{self.backend_id}:vision")
        if self.fail_vision:
            raise ProviderUnavailable(f"{self.backend_id} vision unavailable")
        return ScreenshotEvidence(
            image_role="STATE_DAILY",
            contract="CF2609",
            timeframe="1d",
            blocking_issues=["BAR_CLOSE_UNKNOWN"],
            allowed_usage=EvidenceUsage.QUALITATIVE_ONLY,
            provider=self.backend_id,
            model=(
                "kimi-k3"
                if self.backend_id == "kimi"
                else "gpt-5.6-sol"
            ),
            prompt_version=request.prompt_version,
            image_sha256=f"{self.backend_id}-hash",
        )

    def interpret(self, request):
        raise AssertionError("clarification is not needed")

    def reply(self, request):
        self.calls.append(f"{self.backend_id}:conversation")
        return ConversationReply(
            source_analysis_id=request.source_analysis_id,
            answer=f"{self.backend_id} reply",
            provider=self.backend_id,
            model=(
                "kimi-k3"
                if self.backend_id == "kimi"
                else "gpt-5.6-sol"
            ),
        )


def routed_client(tmp_path, *, fail_kimi_vision: bool = False):
    calls: list[str] = []
    manifests = registry().manifests()

    def make_runtime(backend_id: str, model_id: str) -> AgentRuntime:
        provider = RoutedProvider(
            backend_id,
            calls,
            fail_vision=fail_kimi_vision and backend_id == "kimi",
        )
        return AgentRuntime(
            backend_id=backend_id,
            model_id=model_id,
            vision=provider,
            clarification=provider,
            conversation=provider,
        )

    api = TestClient(
        create_app(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'agents.db'}",
            storage_root=tmp_path / "images",
            agent_backend_registry=AgentBackendRegistry(
                manifests=manifests,
                runtime_factory=make_runtime,
            ),
            privacy_review_token="trusted-review",
        ),
        raise_server_exceptions=False,
    )
    return api, calls


def upload_chart(api: TestClient, case_id: str) -> None:
    response = api.post(
        f"/v1/cases/{case_id}/images",
        headers={
            "Idempotency-Key": f"image-{case_id}",
            "X-Privacy-Review-Token": "trusted-review",
        },
        data={
            "image_role": "STATE_DAILY",
            "role_confirmed": "true",
            "privacy_reviewed": "true",
        },
        files={
            "file": (
                "chart.png",
                b"\x89PNG\r\n\x1a\nfixture",
                "image/png",
            )
        },
    )
    assert response.status_code == 201


def test_lists_agent_backends_and_models() -> None:
    response = client().get("/v1/agent-backends")

    assert response.status_code == 200
    payload = response.json()
    assert [item["backend_id"] for item in payload] == ["codex", "kimi"]
    assert payload[1]["default_model_id"] == "kimi-k3"
    assert payload[1]["models"][0]["display_name"] == "Kimi 3"
    assert payload[1]["models"][1]["available"] is False


def test_new_case_pins_selected_agent_and_model() -> None:
    response = client().post(
        "/v1/cases",
        json={
            "message": "分析这张图。",
            "agent_backend_id": "kimi",
            "agent_model_id": "kimi-k3",
        },
    )

    assert response.status_code == 201
    assert response.json()["agent_backend"] == {
        "backend_id": "kimi",
        "model_id": "kimi-k3",
        "display_name": "Kimi Code",
    }


def test_completed_case_creation_replays_after_agent_becomes_unavailable() -> None:
    agents = registry()
    api = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            agent_backend_registry=agents,
        )
    )
    request = {
        "headers": {"Idempotency-Key": "create-kimi-case"},
        "json": {
            "message": "分析这张图。",
            "agent_backend_id": "kimi",
            "agent_model_id": "kimi-k3",
        },
    }
    first = api.post("/v1/cases", **request)
    agents.manifest("kimi").models[0].available = False
    agents.manifest("kimi").models[0].unavailable_reason = "auth expired"

    replayed = api.post("/v1/cases", **request)

    assert first.status_code == 201
    assert replayed.status_code == 201
    assert replayed.json()["case_id"] == first.json()["case_id"]


def test_new_case_defaults_to_codex() -> None:
    response = client().post("/v1/cases", json={})

    assert response.status_code == 201
    assert response.json()["agent_backend"] == {
        "backend_id": "codex",
        "model_id": "gpt-5.6-sol",
        "display_name": "Codex",
    }


def test_unavailable_model_is_rejected_without_fallback() -> None:
    response = client().post(
        "/v1/cases",
        json={
            "agent_backend_id": "kimi",
            "agent_model_id": "kimi-code/kimi-for-coding",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "缺少 image_in"


def test_switches_agent_and_records_system_message_without_images() -> None:
    api = client()
    case_id = api.post("/v1/cases", json={}).json()["case_id"]

    response = api.post(
        f"/v1/cases/{case_id}/agent-backend",
        headers={"Idempotency-Key": "agent-switch-1"},
        json={"backend_id": "kimi", "model_id": "kimi-k3"},
    )

    assert response.status_code == 200
    assert response.json()["analysis_id"] is None
    conversation = api.get(f"/v1/cases/{case_id}/conversation").json()
    assert conversation["agent_backend"]["backend_id"] == "kimi"
    assert conversation["agent_backend"]["model_id"] == "kimi-k3"
    assert conversation["messages"][-1]["message_type"] == "AGENT_BACKEND_CHANGE"
    assert "Kimi Code" in conversation["messages"][-1]["content"]


def test_selected_agent_handles_vision_and_follow_up(tmp_path) -> None:
    api, calls = routed_client(tmp_path)
    case = api.post(
        "/v1/cases",
        json={
            "contract": "CF2609",
            "agent_backend_id": "kimi",
            "agent_model_id": "kimi-k3",
        },
    ).json()
    upload_chart(api, case["case_id"])

    analysis = api.post(
        f"/v1/cases/{case['case_id']}/analysis",
        headers={"Idempotency-Key": "kimi-analysis"},
    )
    reply = api.post(
        f"/v1/cases/{case['case_id']}/messages",
        headers={"Idempotency-Key": "kimi-follow-up"},
        json={"message": "解释结论"},
    )

    assert analysis.status_code == 200
    assert analysis.json()["agent_backend"]["backend_id"] == "kimi"
    assert analysis.json()["evidence"]["provider"] == "kimi"
    assert reply.status_code == 200
    assert reply.json()["provider"] == "kimi"
    assert calls == ["kimi:vision", "kimi:conversation"]


def test_switch_with_images_reanalyzes_before_committing_selection(
    tmp_path,
) -> None:
    api, calls = routed_client(tmp_path)
    case_id = api.post(
        "/v1/cases",
        json={"contract": "CF2609"},
    ).json()["case_id"]
    upload_chart(api, case_id)
    first = api.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "codex-analysis"},
    ).json()

    switched = api.post(
        f"/v1/cases/{case_id}/agent-backend",
        headers={"Idempotency-Key": "switch-with-image"},
        json={"backend_id": "kimi", "model_id": "kimi-k3"},
    )

    assert switched.status_code == 200
    assert switched.json()["analysis_id"] != first["analysis_id"]
    assert calls == ["codex:vision", "kimi:vision"]
    analyses = api.get(f"/v1/cases/{case_id}/analyses").json()
    assert len(analyses) == 2
    assert analyses[-1]["agent_backend"]["backend_id"] == "kimi"
    conversation = api.get(f"/v1/cases/{case_id}/conversation").json()
    assert conversation["agent_backend"]["backend_id"] == "kimi"
    assert conversation["messages"][-1]["message_type"] == "AGENT_BACKEND_CHANGE"


def test_temporal_switch_with_images_stages_analysis_before_atomic_commit(
    tmp_path,
) -> None:
    captured_commands = []

    async def temporal_executor(command):
        captured_commands.append(command)
        return {
            "analysis_id": command.analysis_id,
            "agent_backend": command.case_state["agent_backend"],
            "milestones": [],
            "decision": {"action": "WAIT_FOR_DATA"},
            "rendered": {"summary": "等待补齐数据"},
            "evidence": {"provider": "kimi", "model": "kimi-k3"},
            "evidence_set": [],
        }

    api = TestClient(
        create_app(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'temporal-switch.db'}",
            storage_root=tmp_path / "images",
            agent_backend_registry=registry(),
            temporal_executor=temporal_executor,
            privacy_review_token="trusted-review",
        ),
        raise_server_exceptions=False,
    )
    case_id = api.post(
        "/v1/cases",
        json={"contract": "CF2609"},
    ).json()["case_id"]
    upload_chart(api, case_id)

    switched = api.post(
        f"/v1/cases/{case_id}/agent-backend",
        headers={"Idempotency-Key": "temporal-switch-with-image"},
        json={"backend_id": "kimi", "model_id": "kimi-k3"},
    )

    assert switched.status_code == 200
    assert len(captured_commands) == 1
    command = captured_commands[0]
    assert command.persist_result is False
    assert command.refresh_vision is True
    assert command.case_state["agent_backend"]["backend_id"] == "kimi"
    analyses = api.get(f"/v1/cases/{case_id}/analyses").json()
    assert [item["analysis_id"] for item in analyses] == [
        switched.json()["analysis_id"]
    ]
    assert analyses[0]["agent_backend"]["backend_id"] == "kimi"
    conversation = api.get(f"/v1/cases/{case_id}/conversation").json()
    assert conversation["agent_backend"]["backend_id"] == "kimi"


def test_failed_switch_reanalysis_keeps_previous_agent_and_conclusion(
    tmp_path,
) -> None:
    api, _ = routed_client(tmp_path, fail_kimi_vision=True)
    case_id = api.post(
        "/v1/cases",
        json={"contract": "CF2609"},
    ).json()["case_id"]
    upload_chart(api, case_id)
    first = api.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "codex-analysis"},
    ).json()

    switched = api.post(
        f"/v1/cases/{case_id}/agent-backend",
        headers={"Idempotency-Key": "failed-switch"},
        json={"backend_id": "kimi", "model_id": "kimi-k3"},
    )

    assert switched.status_code == 503
    conversation = api.get(f"/v1/cases/{case_id}/conversation").json()
    assert conversation["agent_backend"]["backend_id"] == "codex"
    analyses = api.get(f"/v1/cases/{case_id}/analyses").json()
    assert [item["analysis_id"] for item in analyses] == [first["analysis_id"]]


def test_switch_commit_failure_rolls_back_staged_analysis(
    monkeypatch,
    tmp_path,
) -> None:
    api, _ = routed_client(tmp_path)
    case_id = api.post(
        "/v1/cases",
        json={"contract": "CF2609"},
    ).json()["case_id"]
    upload_chart(api, case_id)
    first = api.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "codex-analysis"},
    ).json()
    original_update_case = CaseRepository.update_case

    def fail_agent_selection(self, case_id, state, event_type, payload):
        if event_type == "AGENT_BACKEND_SELECTED":
            raise RuntimeError("forced selection commit failure")
        return original_update_case(self, case_id, state, event_type, payload)

    monkeypatch.setattr(CaseRepository, "update_case", fail_agent_selection)

    switched = api.post(
        f"/v1/cases/{case_id}/agent-backend",
        headers={"Idempotency-Key": "commit-failure"},
        json={"backend_id": "kimi", "model_id": "kimi-k3"},
    )

    assert switched.status_code == 500
    analyses = api.get(f"/v1/cases/{case_id}/analyses").json()
    assert [item["analysis_id"] for item in analyses] == [first["analysis_id"]]
    conversation = api.get(f"/v1/cases/{case_id}/conversation").json()
    assert conversation["agent_backend"]["backend_id"] == "codex"


def test_switch_replays_without_duplicate_reanalysis(tmp_path) -> None:
    api, calls = routed_client(tmp_path)
    case_id = api.post("/v1/cases", json={}).json()["case_id"]
    upload_chart(api, case_id)
    api.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "initial-analysis"},
    )
    request = {
        "headers": {"Idempotency-Key": "replayed-switch"},
        "json": {"backend_id": "kimi", "model_id": "kimi-k3"},
    }

    first = api.post(
        f"/v1/cases/{case_id}/agent-backend",
        **request,
    )
    second = api.post(
        f"/v1/cases/{case_id}/agent-backend",
        **request,
    )

    assert first.status_code == 200
    assert second.json() == first.json()
    assert calls == ["codex:vision", "kimi:vision"]
