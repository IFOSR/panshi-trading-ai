from datetime import datetime, time as datetime_time, timedelta
from pathlib import Path
from threading import Barrier, Event, Lock, Thread, enumerate as enumerate_threads
import time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import trading_agent.api.app as app_module
from trading_agent.api.app import create_app
from trading_agent.db.repositories import CaseRepository
from trading_agent.domain.enums import EvidenceUsage
from trading_agent.domain.evidence import (
    Evidence,
    FactSupport,
    ScreenshotEvidence,
    StrategyEvidenceFacts,
)
from trading_agent.market.bars import MarketBar
from trading_agent.market.resolver import MarketDataSnapshot
from trading_agent.providers.base import ProviderResponseError
from trading_agent.vision.image_quality import MAX_IMAGE_BYTES
from trading_agent.vision.privacy import assess_upload_privacy


def test_complete_case_api_flow() -> None:
    original = b"\x89PNG\r\n\x1a\nfixture"

    class FakeVisionProvider:
        received = b""

        def analyze(self, request):
            self.received = request.image_paths[0].read_bytes()
            return ScreenshotEvidence(
                image_role="STATE_DAILY",
                instrument="rb",
                contract="rb2610",
                timeframe=None,
                cutoff_time=None,
                last_bar_closed=None,
                blocking_issues=["TIMEFRAME_MISSING", "BAR_CLOSE_UNKNOWN"],
                allowed_usage=EvidenceUsage.QUALITATIVE_ONLY,
                provider="fake",
                model="fixture",
                prompt_version=request.prompt_version,
                image_sha256="fixture-hash",
            )

    provider = FakeVisionProvider()
    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            vision_provider=provider,
            privacy_review_token="trusted-review",
        )
    )

    created = client.post(
        "/v1/cases",
        json={"instrument": "rb", "contract": "rb2610"},
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    position = client.post(
        f"/v1/cases/{case_id}/position",
        headers={"Idempotency-Key": "position-1"},
        json={"direction": "FLAT", "quantity": 0},
    )
    assert position.status_code == 200

    image = client.post(
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
        files={"file": ("chart.png", original, "image/png")},
    )
    assert image.status_code == 201

    first = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis-1"},
    )
    repeated = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis-1"},
    )
    assert first.status_code == 200
    assert repeated.json()["analysis_id"] == first.json()["analysis_id"]
    assert len(first.json()["milestones"]) == 8
    assert first.json()["decision"]["action"] == "WAIT_FOR_DATA"
    assert provider.received == original
    assert first.json()["evidence"]["provider"] == "fake"
    assert first.json()["evidence"]["source_image_id"] == image.json()["image_id"]
    assert first.json()["audit"]["model_version"] == "fixture"
    assert first.json()["audit"]["prompt_version"] == "chart-evidence-v2"
    assert first.json()["audit"]["strategy_id"] == "structure_confirmation"
    assert first.json()["audit"]["strategy_version"] == "1.0.0"
    assert first.json()["audit"]["risk_version"] == "china-futures-risk-v1"
    assert len(first.json()["audit"]["rule_versions"]) == 8

    original_response = client.get(
        f"/v1/cases/{case_id}/images/{image.json()['image_id']}"
    )
    assert original_response.content == original

    listed = client.get(f"/v1/cases/{case_id}/analyses")
    assert len(listed.json()) == 1

    fetched = client.get(
        f"/v1/cases/{case_id}/analyses/{first.json()['analysis_id']}"
    )
    assert fetched.status_code == 200

    closed = client.post(f"/v1/cases/{case_id}/close")
    assert closed.json()["lifecycle"] == "CLOSED"


def test_missing_idempotency_key_is_rejected() -> None:
    client = TestClient(create_app(database_url="sqlite+pysqlite:///:memory:"))
    case_id = client.post("/v1/cases", json={}).json()["case_id"]

    response = client.post(f"/v1/cases/{case_id}/analysis")

    assert response.status_code == 400


def test_create_case_replays_same_case_for_same_idempotency_key() -> None:
    client = TestClient(create_app(database_url="sqlite+pysqlite:///:memory:"))
    headers = {"Idempotency-Key": "submission-1:case"}
    payload = {
        "instrument": "rb",
        "contract": "rb2610",
        "message": "判断当前结构。",
        "submission_fingerprint": "a" * 64,
    }

    first = client.post("/v1/cases", headers=headers, json=payload)
    repeated = client.post("/v1/cases", headers=headers, json=payload)

    assert first.status_code == 201
    assert repeated.status_code == 201
    assert repeated.json()["case_id"] == first.json()["case_id"]


def test_create_case_rejects_changed_payload_for_same_idempotency_key() -> None:
    client = TestClient(create_app(database_url="sqlite+pysqlite:///:memory:"))
    headers = {"Idempotency-Key": "submission-1:case"}

    first = client.post(
        "/v1/cases",
        headers=headers,
        json={
            "contract": "rb2610",
            "message": "判断当前结构。",
            "submission_fingerprint": "a" * 64,
        },
    )
    changed = client.post(
        "/v1/cases",
        headers=headers,
        json={
            "contract": "rb2610",
            "message": "判断当前结构。",
            "submission_fingerprint": "b" * 64,
        },
    )

    assert first.status_code == 201
    assert changed.status_code == 409
    assert changed.json()["detail"] == "idempotency key payload mismatch"


def test_concurrent_create_case_replays_one_deterministic_case(tmp_path) -> None:
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'concurrent-create.db'}"
    )
    barrier = Barrier(3)
    responses = []
    response_lock = Lock()
    payload = {
        "contract": "rb2610",
        "message": "判断当前结构。",
        "submission_fingerprint": "a" * 64,
    }

    def create() -> None:
        client = TestClient(app)
        barrier.wait()
        response = client.post(
            "/v1/cases",
            headers={"Idempotency-Key": "submission-1:case"},
            json=payload,
        )
        with response_lock:
            responses.append(response)

    threads = [Thread(target=create), Thread(target=create)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert [response.status_code for response in responses] == [201, 201]
    assert len({response.json()["case_id"] for response in responses}) == 1


def test_concurrent_create_case_rejects_changed_payload(tmp_path) -> None:
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'concurrent-conflict.db'}"
    )
    barrier = Barrier(3)
    responses = []
    response_lock = Lock()

    def create(fingerprint: str) -> None:
        client = TestClient(app)
        barrier.wait()
        response = client.post(
            "/v1/cases",
            headers={"Idempotency-Key": "submission-1:case"},
            json={
                "contract": "rb2610",
                "message": "判断当前结构。",
                "submission_fingerprint": fingerprint,
            },
        )
        with response_lock:
            responses.append(response)

    threads = [
        Thread(target=create, args=("a" * 64,)),
        Thread(target=create, args=("b" * 64,)),
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert sorted(response.status_code for response in responses) == [201, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["detail"] == "idempotency key payload mismatch"


def test_missing_case_analysis_list_returns_not_found() -> None:
    client = TestClient(create_app(database_url="sqlite+pysqlite:///:memory:"))

    response = client.get("/v1/cases/missing/analyses")

    assert response.status_code == 404


def test_default_app_reads_database_url_from_environment(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'configured.db'}"
    monkeypatch.setenv("TRADING_AGENT_DATABASE_URL", database_url)

    app = create_app()

    assert app.state.database_url == database_url


def test_temporal_executor_owns_analysis_when_configured(tmp_path) -> None:
    called = False
    captured_command = None

    class ProviderMustNotRun:
        def analyze(self, request):
            raise AssertionError("API must not run provider when Temporal is configured")

    async def temporal_executor(command):
        nonlocal called, captured_command
        called = True
        captured_command = command
        return {
            "analysis_id": "temporal-analysis",
            "milestones": [{"number": number} for number in range(1, 9)],
            "decision": {"action": "WAIT_FOR_DATA"},
            "rendered": {"summary": "等待补齐数据"},
            "evidence": {"provider": "codex"},
        }

    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
            vision_provider=ProviderMustNotRun(),
            temporal_executor=temporal_executor,
            privacy_review_token="trusted-review",
        )
    )
    case_id = client.post("/v1/cases", json={}).json()["case_id"]
    client.post(
        f"/v1/cases/{case_id}/images",
        headers={
            "Idempotency-Key": "image",
            "X-Privacy-Review-Token": "trusted-review",
        },
        data={
            "image_role": "STATE_DAILY",
            "role_confirmed": "true",
            "privacy_reviewed": "true",
        },
        files={"file": ("chart.png", b"\x89PNG\r\n\x1a\nfixture", "image/png")},
    ).raise_for_status()

    response = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis"},
    )

    assert response.status_code == 200
    assert response.json()["analysis_id"] == "temporal-analysis"
    assert called is True
    assert captured_command is not None
    assert captured_command.case_state["case_id"] == case_id
    assert captured_command.case_state["strategy"] == {
        "strategy_id": "structure_confirmation",
        "version": "1.0.0",
        "display_name": "结构确认策略",
    }
    assert captured_command.case_version >= 2
    assert captured_command.previous_analysis is None


def test_provider_strategy_facts_change_api_milestones(tmp_path) -> None:
    class FactProvider:
        def analyze(self, request):
            return ScreenshotEvidence(
                image_role="STATE_DAILY",
                instrument="rb",
                contract="rb2610",
                timeframe="1d",
                cutoff_time="2026-07-20",
                last_bar_closed=True,
                allowed_usage=EvidenceUsage.QUALITATIVE_ONLY,
                provider="codex",
                model="gpt-5.6-sol",
                prompt_version=request.prompt_version,
                image_sha256="fixture",
                    strategy_facts=StrategyEvidenceFacts(
                    trend_bias="BEARISH",
                    price_location="BELOW_BOLL_MID_ABOVE_LOWER",
                    volume_state="BELOW_BOTH_AVERAGES",
                    momentum_state="BEARISH_RECOVERY",
                        position_behavior="LONG_BUILD_SHORT_COVER",
                    ),
                    observations=[
                        Evidence(
                            evidence_id=f"support-{field}",
                            kind=field,
                            value="visible",
                            confidence=0.95,
                            provenance="codex:gpt-5.6-sol",
                        )
                        for field in (
                            "trend_bias",
                            "price_location",
                            "volume_state",
                            "momentum_state",
                            "position_behavior",
                        )
                    ],
                    strategy_fact_support={
                        field: FactSupport(
                            confidence=0.95,
                            evidence_refs=[f"support-{field}"],
                        )
                        for field in (
                            "trend_bias",
                            "price_location",
                            "volume_state",
                            "momentum_state",
                            "position_behavior",
                        )
                    },
                )

    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
            vision_provider=FactProvider(),
            privacy_review_token="trusted-review",
        )
    )
    case_id = client.post(
        "/v1/cases", json={"contract": "rb2610"}
    ).json()["case_id"]
    client.post(
        f"/v1/cases/{case_id}/images",
        headers={
            "Idempotency-Key": "image",
            "X-Privacy-Review-Token": "trusted-review",
        },
        data={
            "image_role": "STATE_DAILY",
            "role_confirmed": "true",
            "privacy_reviewed": "true",
        },
        files={"file": ("chart.png", b"\x89PNG\r\n\x1a\nfixture", "image/png")},
    ).raise_for_status()

    response = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis"},
    )
    response.raise_for_status()
    steps = {step["number"]: step for step in response.json()["milestones"]}

    assert steps[2]["result"] == "U_BEARISH_BIAS"
    assert steps[4]["result"] == "BELOW_BOLL_MID_ABOVE_LOWER"
    assert steps[5]["status"] == "CANDIDATE"
    assert steps[6]["result"] == "BEARISH_RECOVERY"


def test_structured_market_data_overrides_model_facts_in_api_pipeline(tmp_path) -> None:
    class ModelProvider:
        def analyze(self, request):
            return ScreenshotEvidence(
                image_role="STATE_DAILY",
                contract="rb2610",
                timeframe="1d",
                last_bar_closed=None,
                provider="codex",
                model="gpt-5.6-sol",
                prompt_version=request.prompt_version,
                image_sha256="fixture",
            )

    class Resolver:
        requested_timeframes: list[str] = []

        def resolve(self, case_state, evidence):
            timeframe = evidence.timeframe or "1d"
            self.requested_timeframes.append(timeframe)
            now = datetime.now(ZoneInfo("Asia/Shanghai"))
            if now.weekday() in {5, 6}:
                latest_friday = now.date() - timedelta(days=now.weekday() - 4)
                latest = datetime.combine(
                        latest_friday,
                        (
                            datetime_time(23, 0)
                            if timeframe == "60m"
                            else datetime_time(15, 0)
                        ),
                    tzinfo=ZoneInfo("Asia/Shanghai"),
                )
            else:
                latest = now - timedelta(hours=1)
            interval = timedelta(hours=1) if timeframe == "60m" else timedelta(days=1)
            start = latest - interval * 29
            bars = [
                MarketBar(
                    contract="rb2610",
                    timeframe=timeframe,
                    timestamp=start + interval * index,
                    trading_date=(start + interval * index).date(),
                    open=100 + index,
                    high=102 + index,
                    low=99 + index,
                    close=101 + index,
                    volume=1000 + index,
                    open_interest=5000 + index * 10,
                    settlement=101 + index,
                    is_closed=True,
                    source="fixture",
                )
                for index in range(30)
            ]
            return MarketDataSnapshot(
                contract="rb2610",
                timeframe=timeframe,
                cutoff_time=bars[-1].timestamp,
                last_bar_closed=True,
                price_axis_verified=True,
                rollover_active=False,
                near_price_limit=False,
                sources=["fixture-market"],
                validation_sources=["fixture-exchange"],
                bars=bars,
            )

    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
            vision_provider=ModelProvider(),
            market_data_resolver=Resolver(),
            privacy_review_token="trusted-review",
        )
    )
    case_id = client.post(
        "/v1/cases", json={"contract": "rb2610"}
    ).json()["case_id"]
    client.post(
        f"/v1/cases/{case_id}/images",
        headers={
            "Idempotency-Key": "image",
            "X-Privacy-Review-Token": "trusted-review",
        },
        data={
            "image_role": "STATE_DAILY",
            "role_confirmed": "true",
            "privacy_reviewed": "true",
        },
        files={"file": ("chart.png", b"\x89PNG\r\n\x1a\nfixture", "image/png")},
    ).raise_for_status()

    response = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis"},
    )
    response.raise_for_status()
    payload = response.json()
    steps = {step["number"]: step for step in payload["milestones"]}

    assert payload["evidence"]["field_provenance"]["strategy_facts.price_location"] == (
        "structured_market_data"
    )
    assert steps[1]["status"] == "CONFIRMED"
    assert steps[1]["details"]["sources"] == ["fixture-market"]
    assert Resolver.requested_timeframes == ["1d", "60m"]
    assert steps[1]["details"]["validation_sources"] == ["fixture-exchange"]
    assert steps[4]["result"] != "UNKNOWN"
    assert steps[5]["status"] == "CONFIRMED"
    clarifications = client.get(
        f"/v1/cases/{case_id}/clarifications"
    ).json()
    assert clarifications["questions"] == []


def test_new_case_position_is_unknown_until_user_confirms_it() -> None:
    client = TestClient(create_app(database_url="sqlite+pysqlite:///:memory:"))

    created = client.post("/v1/cases", json={})

    assert created.json()["position"]["direction"] == "UNKNOWN"


def test_risk_parameters_are_persisted_as_case_state() -> None:
    client = TestClient(create_app(database_url="sqlite+pysqlite:///:memory:"))
    case_id = client.post("/v1/cases", json={}).json()["case_id"]

    updated = client.post(
        f"/v1/cases/{case_id}/risk",
        headers={"Idempotency-Key": "risk-1"},
        json={
            "account_risk_limit": 0.01,
            "proposed_risk": 0.005,
            "max_stop_distance_ratio": 0.03,
            "correlated_exposure_exceeded": False,
        },
    )
    replayed = client.get(f"/v1/cases/{case_id}")

    assert updated.status_code == 200
    assert replayed.json()["risk"] == updated.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"direction": "LONG", "quantity": 0},
        {"direction": "SHORT", "quantity": -1},
        {"direction": "FLAT", "quantity": 1},
        {"direction": "LONG", "quantity": 1, "average_cost": -1},
        {"direction": "SHORT", "quantity": 1, "stop_price": -1},
    ],
)
def test_position_api_rejects_impossible_states(payload) -> None:
    client = TestClient(create_app(database_url="sqlite+pysqlite:///:memory:"))
    case_id = client.post("/v1/cases", json={}).json()["case_id"]

    response = client.post(
        f"/v1/cases/{case_id}/position",
        headers={"Idempotency-Key": "position-invalid"},
        json=payload,
    )

    assert response.status_code == 422


def test_reanalysis_reuses_cached_evidence_for_unchanged_active_image(tmp_path) -> None:
    class CountingProvider:
        calls = 0

        def analyze(self, request):
            self.calls += 1
            return ScreenshotEvidence(
                image_role="STATE_DAILY",
                contract="rb2610",
                timeframe="1d",
                last_bar_closed=True,
                provider="codex",
                model="gpt-5.6-sol",
                prompt_version=request.prompt_version,
                image_sha256="fixture",
            )

    provider = CountingProvider()
    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
            vision_provider=provider,
            privacy_review_token="trusted-review",
        )
    )
    case_id = client.post(
        "/v1/cases",
        json={"contract": "rb2610"},
    ).json()["case_id"]
    client.post(
        f"/v1/cases/{case_id}/images",
        headers={
            "Idempotency-Key": "image",
            "X-Privacy-Review-Token": "trusted-review",
        },
        data={
            "image_role": "STATE_DAILY",
            "role_confirmed": "true",
            "privacy_reviewed": "true",
        },
        files={"file": ("chart.png", b"\x89PNG\r\n\x1a\nfixture", "image/png")},
    ).raise_for_status()

    client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis-1"},
    ).raise_for_status()
    client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis-2"},
    ).raise_for_status()

    assert provider.calls == 1


def test_only_latest_image_per_role_enters_analysis(tmp_path) -> None:
    class Provider:
        calls = 0

        def analyze(self, request):
            self.calls += 1
            return ScreenshotEvidence(
                image_role="STATE_DAILY",
                contract="rb2610",
                timeframe="1d",
                last_bar_closed=True,
                provider="codex",
                model="gpt-5.6-sol",
                prompt_version=request.prompt_version,
                image_sha256="latest",
            )

    provider = Provider()
    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
            vision_provider=provider,
            privacy_review_token="trusted-review",
        )
    )
    case_id = client.post(
        "/v1/cases",
        json={"contract": "rb2610"},
    ).json()["case_id"]
    client.post(
        f"/v1/cases/{case_id}/images",
        headers={"Idempotency-Key": "old"},
        data={
            "image_role": "STATE_DAILY",
            "role_confirmed": "true",
            "privacy_reviewed": "false",
        },
        files={"file": ("old.png", b"\x89PNG\r\n\x1a\nold", "image/png")},
    ).raise_for_status()
    client.post(
        f"/v1/cases/{case_id}/images",
        headers={
            "Idempotency-Key": "latest",
            "X-Privacy-Review-Token": "trusted-review",
        },
        data={
            "image_role": "STATE_DAILY",
            "role_confirmed": "true",
            "privacy_reviewed": "true",
        },
        files={"file": ("latest.png", b"\x89PNG\r\n\x1a\nlatest", "image/png")},
    ).raise_for_status()

    response = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis"},
    )
    response.raise_for_status()

    assert provider.calls == 1
    assert len(response.json()["evidence_set"]) == 1
    assert "PRIVACY_REVIEW_REQUIRED" not in response.json()["decision"]["reason_codes"]


def test_natural_language_message_populates_auditable_case_inputs() -> None:
    client = TestClient(create_app(database_url="sqlite+pysqlite:///:memory:"))

    created = client.post(
        "/v1/cases",
        json={
            "message": (
                "请分析 rb2610，我有2手多单，成本3500，止损3450，"
                "计划持有3天，单笔风险1%，用于持仓管理。"
            )
        },
    )

    assert created.status_code == 201
    state = created.json()
    assert state["contract"] == "rb2610"
    assert state["position"] == {
        "direction": "LONG",
        "quantity": 2,
        "average_cost": 3500.0,
        "stop_price": 3450.0,
    }
    assert state["risk"]["account_risk_limit"] == 0.01
    assert state["user_input"]["decision_intent"] == "POSITION_MANAGEMENT"
    assert state["user_input"]["holding_period"] == "3天"


def test_natural_language_position_without_quantity_is_not_persisted_as_zero() -> None:
    client = TestClient(create_app(database_url="sqlite+pysqlite:///:memory:"))

    created = client.post(
        "/v1/cases",
        json={"message": "我有多单，接下来该如何操作"},
    )

    assert created.status_code == 201
    assert created.json()["position"] == {
        "direction": "LONG",
        "quantity": None,
        "average_cost": None,
        "stop_price": None,
    }


def test_configured_api_token_protects_case_and_raw_image_routes(tmp_path) -> None:
    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
            api_token="secret-token",
        )
    )

    unauthorized = client.post("/v1/cases", json={})
    authorized = client.post(
        "/v1/cases",
        headers={"Authorization": "Bearer secret-token"},
        json={},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 201


def test_production_api_without_token_fails_closed() -> None:
    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            environment="production",
        )
    )

    response = client.post("/v1/cases", json={})

    assert response.status_code == 503
    assert response.json()["detail"] == "api authentication is not configured"


def test_unreviewed_image_is_not_sent_to_model_even_if_client_sets_legacy_safe_flag(
    tmp_path,
) -> None:
    class ProviderMustNotRun:
        def analyze(self, request):
            raise AssertionError("unreviewed image must not be sent")

    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
            vision_provider=ProviderMustNotRun(),
        )
    )
    case_id = client.post("/v1/cases", json={}).json()["case_id"]
    uploaded = client.post(
        f"/v1/cases/{case_id}/images",
        headers={"Idempotency-Key": "image"},
        data={
            "image_role": "STATE_DAILY",
            "role_confirmed": "true",
            "privacy_reviewed": "false",
            "safe_for_model": "true",
        },
        files={"file": ("chart.png", b"\x89PNG\r\n\x1a\nfixture", "image/png")},
    )
    uploaded.raise_for_status()

    response = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis"},
    )
    response.raise_for_status()

    assert uploaded.json()["safe_for_model"] is False
    assert response.json()["evidence"]["provider"] == "privacy-gate"
    assert response.json()["evidence"]["source_image_id"] == uploaded.json()["image_id"]
    assert response.json()["decision"]["action"] == "WAIT_FOR_DATA"


@pytest.mark.parametrize(
    ("filename", "content", "expected_detail"),
    [
        ("chart.txt", b"not an image", "unsupported image extension"),
        ("chart.png", b"not really a png", "invalid PNG signature"),
    ],
)
def test_upload_rejects_invalid_original_image_before_persistence(
    tmp_path,
    filename,
    content,
    expected_detail,
) -> None:
    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
        )
    )
    case_id = client.post("/v1/cases", json={}).json()["case_id"]

    response = client.post(
        f"/v1/cases/{case_id}/images",
        headers={"Idempotency-Key": "invalid-image"},
        files={"file": (filename, content, "application/octet-stream")},
    )

    assert response.status_code == 400
    assert expected_detail in response.json()["detail"]
    assert list(tmp_path.rglob("*")) == []
    assert client.get(f"/v1/cases/{case_id}").json()["images"] == []


def test_upload_rejects_image_over_maximum_size_before_persistence(tmp_path) -> None:
    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
        )
    )
    case_id = client.post("/v1/cases", json={}).json()["case_id"]

    response = client.post(
        f"/v1/cases/{case_id}/images",
        headers={"Idempotency-Key": "oversized-image"},
        files={
            "file": (
                "chart.png",
                b"\x89PNG\r\n\x1a\n" + b"x" * MAX_IMAGE_BYTES,
                "image/png",
            )
        },
    )

    assert response.status_code == 413
    assert list(tmp_path.rglob("*")) == []
    assert client.get(f"/v1/cases/{case_id}").json()["images"] == []


def test_duplicate_original_image_hash_reuses_existing_upload(tmp_path) -> None:
    original = (Path("tests/fixtures/charts/daily_boll_macd_volume.png")).read_bytes()
    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
        )
    )
    case_id = client.post("/v1/cases", json={}).json()["case_id"]

    first = client.post(
        f"/v1/cases/{case_id}/images",
        headers={"Idempotency-Key": "image-first"},
        data={"image_role": "STATE_DAILY"},
        files={"file": ("chart.png", original, "image/png")},
    )
    duplicate = client.post(
        f"/v1/cases/{case_id}/images",
        headers={"Idempotency-Key": "image-duplicate"},
        data={"image_role": "STATE_DAILY"},
        files={"file": ("chart.png", original, "image/png")},
    )
    replayed_duplicate = client.post(
        f"/v1/cases/{case_id}/images",
        headers={"Idempotency-Key": "image-duplicate"},
        data={"image_role": "STATE_DAILY"},
        files={"file": ("chart.png", original, "image/png")},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert replayed_duplicate.status_code == 200
    assert duplicate.json()["image_id"] == first.json()["image_id"]
    assert replayed_duplicate.json() == duplicate.json()
    assert duplicate.json()["duplicate"] is True
    state = client.get(f"/v1/cases/{case_id}").json()
    assert state["image_ids"] == [first.json()["image_id"]]
    assert len(list(tmp_path.rglob("*.png"))) == 1


def test_delete_case_permanently_removes_records_and_original_images(tmp_path) -> None:
    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
        )
    )
    deleted_case_id = client.post(
        "/v1/cases",
        json={"contract": "cf2609"},
    ).json()["case_id"]
    retained_case_id = client.post(
        "/v1/cases",
        json={"contract": "rb2610"},
    ).json()["case_id"]
    uploaded = client.post(
        f"/v1/cases/{deleted_case_id}/images",
        headers={"Idempotency-Key": "delete-image"},
        files={
            "file": (
                "chart.png",
                b"\x89PNG\r\n\x1a\nfixture",
                "image/png",
            )
        },
    )
    uploaded.raise_for_status()
    image_path = Path(uploaded.json()["path"])

    deleted = client.delete(f"/v1/cases/{deleted_case_id}")
    repeated = client.delete(f"/v1/cases/{deleted_case_id}")

    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": 1}
    assert repeated.status_code == 200
    assert repeated.json() == {"deleted": 0}
    assert client.get(f"/v1/cases/{deleted_case_id}").status_code == 404
    assert client.get(f"/v1/cases/{retained_case_id}").status_code == 200
    assert not image_path.exists()
    assert not (tmp_path / deleted_case_id).exists()


def test_delete_all_cases_permanently_clears_history_and_images(tmp_path) -> None:
    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
        )
    )
    case_ids: list[str] = []
    for index, contract in enumerate(("cf2609", "rb2610"), start=1):
        case_id = client.post(
            "/v1/cases",
            json={"contract": contract},
        ).json()["case_id"]
        case_ids.append(case_id)
        uploaded = client.post(
            f"/v1/cases/{case_id}/images",
            headers={"Idempotency-Key": f"bulk-image-{index}"},
            files={
                "file": (
                    f"chart-{index}.png",
                    b"\x89PNG\r\n\x1a\nfixture" + bytes([index]),
                    "image/png",
                )
            },
        )
        uploaded.raise_for_status()

    deleted = client.delete("/v1/cases")
    repeated = client.delete("/v1/cases")

    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": 2}
    assert repeated.status_code == 200
    assert repeated.json() == {"deleted": 0}
    assert client.get("/v1/cases").json() == []
    assert all(not (tmp_path / case_id).exists() for case_id in case_ids)


def test_case_history_lists_every_case_that_clear_all_will_delete() -> None:
    client = TestClient(create_app(database_url="sqlite+pysqlite:///:memory:"))
    for index in range(55):
        client.post(
            "/v1/cases",
            json={"contract": f"zz{index:04d}"},
        ).raise_for_status()

    history = client.get("/v1/cases")

    assert history.status_code == 200
    assert len(history.json()) == 55


def test_delete_case_restores_quarantined_images_when_database_delete_fails(
    monkeypatch,
    tmp_path,
) -> None:
    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
        ),
        raise_server_exceptions=False,
    )
    case_id = client.post(
        "/v1/cases",
        json={"contract": "cf2609"},
    ).json()["case_id"]
    uploaded = client.post(
        f"/v1/cases/{case_id}/images",
        headers={"Idempotency-Key": "rollback-image"},
        files={
            "file": (
                "chart.png",
                b"\x89PNG\r\n\x1a\nfixture",
                "image/png",
            )
        },
    )
    uploaded.raise_for_status()
    image_path = Path(uploaded.json()["path"])

    def fail_delete(_repository, _case_id):
        raise RuntimeError("database delete failed")

    monkeypatch.setattr(CaseRepository, "delete_case", fail_delete)

    response = client.delete(f"/v1/cases/{case_id}")

    assert response.status_code == 500
    assert client.get(f"/v1/cases/{case_id}").status_code == 200
    assert image_path.exists()
    assert list((tmp_path / ".trash").glob("*")) == []


def test_delete_case_retries_deferred_file_cleanup_without_restart(
    monkeypatch,
    tmp_path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'cleanup-recovery.db'}"
    image_root = tmp_path / "images"
    client = TestClient(
        create_app(
            database_url=database_url,
            storage_root=image_root,
        ),
        raise_server_exceptions=False,
    )
    case_id = client.post(
        "/v1/cases",
        json={"contract": "cf2609"},
    ).json()["case_id"]
    client.post(
        f"/v1/cases/{case_id}/images",
        headers={"Idempotency-Key": "cleanup-image"},
        files={
            "file": (
                "chart.png",
                b"\x89PNG\r\n\x1a\nfixture",
                "image/png",
            )
        },
    ).raise_for_status()
    original_purge = app_module._purge_quarantined_images
    allow_cleanup = Event()

    def fail_until_released(operation_root):
        if not allow_cleanup.is_set():
            raise OSError("simulated cleanup failure")
        original_purge(operation_root)

    monkeypatch.setattr(
        app_module,
        "_purge_quarantined_images",
        fail_until_released,
    )

    deleted = client.delete(f"/v1/cases/{case_id}")

    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": 1}
    assert client.get(f"/v1/cases/{case_id}").status_code == 404
    assert list((image_root / ".trash").glob("*"))
    allow_cleanup.set()
    deadline = time.monotonic() + 3
    while (image_root / ".trash").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not (image_root / ".trash").exists()


def test_deferred_file_cleanup_uses_one_worker_for_multiple_operations(
    monkeypatch,
    tmp_path,
) -> None:
    image_root = tmp_path / "images"
    client = TestClient(
        create_app(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'cleanup-worker.db'}",
            storage_root=image_root,
        ),
        raise_server_exceptions=False,
    )
    case_ids: list[str] = []
    for index, contract in enumerate(("cf2609", "rb2610"), start=1):
        case_id = client.post(
            "/v1/cases",
            json={"contract": contract},
        ).json()["case_id"]
        case_ids.append(case_id)
        client.post(
            f"/v1/cases/{case_id}/images",
            headers={"Idempotency-Key": f"cleanup-worker-image-{index}"},
            files={
                "file": (
                    f"chart-{index}.png",
                    b"\x89PNG\r\n\x1a\nfixture" + bytes([index]),
                    "image/png",
                )
            },
        ).raise_for_status()
    original_purge = app_module._purge_quarantined_images
    allow_cleanup = Event()

    def fail_until_released(operation_root):
        if not allow_cleanup.is_set():
            raise OSError("simulated persistent cleanup failure")
        original_purge(operation_root)

    monkeypatch.setattr(
        app_module,
        "_purge_quarantined_images",
        fail_until_released,
    )

    for case_id in case_ids:
        client.delete(f"/v1/cases/{case_id}").raise_for_status()
    cleanup_threads = [
        thread
        for thread in enumerate_threads()
        if thread.name.startswith("deletion-cleanup-")
    ]

    assert len(cleanup_threads) == 1
    allow_cleanup.set()
    deadline = time.monotonic() + 3
    while (image_root / ".trash").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not (image_root / ".trash").exists()


def test_startup_restores_quarantined_images_when_case_still_exists(
    tmp_path,
) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'restore-on-startup.db'}"
    image_root = tmp_path / "images"
    client = TestClient(
        create_app(
            database_url=database_url,
            storage_root=image_root,
        )
    )
    case_id = client.post(
        "/v1/cases",
        json={"contract": "cf2609"},
    ).json()["case_id"]
    uploaded = client.post(
        f"/v1/cases/{case_id}/images",
        headers={"Idempotency-Key": "startup-restore-image"},
        files={
            "file": (
                "chart.png",
                b"\x89PNG\r\n\x1a\nfixture",
                "image/png",
            )
        },
    )
    uploaded.raise_for_status()
    image_path = Path(uploaded.json()["path"])
    app_module._quarantine_case_images(image_root, [case_id])

    assert not image_path.exists()
    assert list((image_root / ".trash").glob("*"))

    recovered = TestClient(
        create_app(
            database_url=database_url,
            storage_root=image_root,
        )
    )

    assert recovered.get(f"/v1/cases/{case_id}").status_code == 200
    assert image_path.exists()
    assert not (image_root / ".trash").exists()


def test_delete_all_serializes_concurrent_case_creation(
    monkeypatch,
    tmp_path,
) -> None:
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'delete-create.db'}",
        storage_root=tmp_path / "images",
    )
    setup_client = TestClient(app)
    setup_client.post("/v1/cases", json={"contract": "cf2609"}).raise_for_status()
    delete_entered = Event()
    release_delete = Event()
    create_finished = Event()
    original_delete_all = CaseRepository.delete_all_cases
    responses: dict[str, object] = {}

    def delayed_delete_all(repository):
        delete_entered.set()
        assert release_delete.wait(timeout=5)
        return original_delete_all(repository)

    monkeypatch.setattr(
        CaseRepository,
        "delete_all_cases",
        delayed_delete_all,
    )

    def delete_all() -> None:
        responses["delete"] = TestClient(app).delete("/v1/cases")

    def create_case() -> None:
        responses["create"] = TestClient(app).post(
            "/v1/cases",
            json={"contract": "rb2610"},
        )
        create_finished.set()

    delete_thread = Thread(target=delete_all)
    delete_thread.start()
    assert delete_entered.wait(timeout=5)
    create_thread = Thread(target=create_case)
    create_thread.start()
    create_was_serialized = not create_finished.wait(timeout=0.2)
    release_delete.set()
    delete_thread.join(timeout=5)
    create_thread.join(timeout=5)

    assert create_was_serialized
    assert not delete_thread.is_alive()
    assert not create_thread.is_alive()
    assert responses["delete"].status_code == 200
    assert responses["create"].status_code == 201
    remaining = setup_client.get("/v1/cases").json()
    assert [item["contract"] for item in remaining] == ["rb2610"]


def test_delete_case_serializes_concurrent_image_upload(
    monkeypatch,
    tmp_path,
) -> None:
    image_root = tmp_path / "images"
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'delete-upload.db'}",
        storage_root=image_root,
    )
    setup_client = TestClient(app)
    case_id = setup_client.post(
        "/v1/cases",
        json={"contract": "cf2609"},
    ).json()["case_id"]
    delete_entered = Event()
    release_delete = Event()
    upload_finished = Event()
    original_delete_case = CaseRepository.delete_case
    responses: dict[str, object] = {}

    def delayed_delete_case(repository, deleted_case_id):
        delete_entered.set()
        assert release_delete.wait(timeout=5)
        return original_delete_case(repository, deleted_case_id)

    monkeypatch.setattr(
        CaseRepository,
        "delete_case",
        delayed_delete_case,
    )

    def delete_case() -> None:
        responses["delete"] = TestClient(app).delete(f"/v1/cases/{case_id}")

    def upload_image() -> None:
        responses["upload"] = TestClient(app).post(
            f"/v1/cases/{case_id}/images",
            headers={"Idempotency-Key": "concurrent-image"},
            files={
                "file": (
                    "chart.png",
                    b"\x89PNG\r\n\x1a\nfixture",
                    "image/png",
                )
            },
        )
        upload_finished.set()

    delete_thread = Thread(target=delete_case)
    delete_thread.start()
    assert delete_entered.wait(timeout=5)
    upload_thread = Thread(target=upload_image)
    upload_thread.start()
    upload_was_serialized = not upload_finished.wait(timeout=0.2)
    release_delete.set()
    delete_thread.join(timeout=5)
    upload_thread.join(timeout=5)

    assert upload_was_serialized
    assert not delete_thread.is_alive()
    assert not upload_thread.is_alive()
    assert responses["delete"].status_code == 200
    assert responses["upload"].status_code == 404
    assert not (image_root / case_id).exists()


def test_client_role_and_checkbox_cannot_self_approve_external_model_transmission() -> None:
    assessment = assess_upload_privacy(
        image_role="STATE_DAILY",
        role_confirmed=True,
        privacy_reviewed=True,
    )

    assert assessment.safe_for_model is False


def test_confirmed_roles_route_all_images_and_override_model_role(tmp_path) -> None:
    class RoleBlindProvider:
        seen_contexts: list[str] = []

        def analyze(self, request):
            self.seen_contexts.append(request.user_context or "")
            is_execution = "EXECUTION_60M" in (request.user_context or "")
            return ScreenshotEvidence(
                image_role="AUXILIARY",
                contract="rb2610",
                timeframe="60m" if is_execution else "1d",
                last_bar_closed=True,
                provider="codex",
                model="gpt-5.6-sol",
                prompt_version=request.prompt_version,
                image_sha256="fixture",
                strategy_facts=StrategyEvidenceFacts(
                    trend_bias="BULLISH",
                    price_location="BETWEEN_UPPER_AND_MID",
                    price_confirmation=True if is_execution else None,
                    price_confirmation_direction=(
                        "BULLISH" if is_execution else "UNKNOWN"
                    ),
                    price_confirmation_type=(
                        "PULLBACK" if is_execution else "UNKNOWN"
                    ),
                ),
            )

    provider = RoleBlindProvider()
    client = TestClient(
        create_app(
            database_url="sqlite+pysqlite:///:memory:",
            storage_root=tmp_path,
            vision_provider=provider,
            privacy_review_token="trusted-review",
        )
    )
    case_id = client.post(
        "/v1/cases", json={"contract": "rb2610"}
    ).json()["case_id"]
    for key, role in (("daily", "STATE_DAILY"), ("execution", "EXECUTION_60M")):
        client.post(
            f"/v1/cases/{case_id}/images",
            headers={
                "Idempotency-Key": key,
                "X-Privacy-Review-Token": "trusted-review",
            },
            data={
                "image_role": role,
                "role_confirmed": "true",
                "privacy_reviewed": "true",
            },
            files={"file": (f"{key}.png", b"\x89PNG\r\n\x1a\nfixture", "image/png")},
        ).raise_for_status()

    response = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis"},
    )
    response.raise_for_status()
    payload = response.json()

    assert len(provider.seen_contexts) == 2
    assert [item["image_role"] for item in payload["evidence_set"]] == [
        "STATE_DAILY",
        "EXECUTION_60M",
    ]


def test_slow_multi_image_analysis_keeps_idempotency_lease_during_extraction(
    monkeypatch,
    tmp_path,
) -> None:
    first_provider_call_started = Event()
    release_first_provider_call = Event()

    class SlowProvider:
        def __init__(self) -> None:
            self.calls = 0
            self.lock = Lock()

        def analyze(self, request):
            with self.lock:
                self.calls += 1
                call_number = self.calls
            if call_number == 1:
                first_provider_call_started.set()
                assert release_first_provider_call.wait(timeout=5)
            is_execution = "EXECUTION_60M" in (request.user_context or "")
            return ScreenshotEvidence(
                image_role="EXECUTION_60M" if is_execution else "STATE_DAILY",
                contract="rb2610",
                timeframe="60m" if is_execution else "1d",
                last_bar_closed=True,
                provider="slow",
                model="fixture",
                prompt_version=request.prompt_version,
                image_sha256=f"fixture-{call_number}",
            )

    monkeypatch.setattr(
        CaseRepository,
        "idempotency_lease",
        timedelta(milliseconds=120),
    )
    provider = SlowProvider()
    database_url = f"sqlite+pysqlite:///{tmp_path / 'lease.db'}"
    app = create_app(
        database_url=database_url,
        storage_root=tmp_path / "images",
        vision_provider=provider,
        privacy_review_token="trusted-review",
    )
    setup_client = TestClient(app)
    case_id = setup_client.post(
        "/v1/cases",
        json={"contract": "rb2610"},
    ).json()["case_id"]
    for key, role in (("daily", "STATE_DAILY"), ("execution", "EXECUTION_60M")):
        setup_client.post(
            f"/v1/cases/{case_id}/images",
            headers={
                "Idempotency-Key": key,
                "X-Privacy-Review-Token": "trusted-review",
            },
            data={
                "image_role": role,
                "role_confirmed": "true",
                "privacy_reviewed": "true",
            },
            files={
                "file": (
                    f"{key}.png",
                    b"\x89PNG\r\n\x1a\n" + key.encode(),
                    "image/png",
                )
            },
        ).raise_for_status()

    first_result: dict[str, object] = {}

    def run_first_analysis() -> None:
        client = TestClient(app)
        first_result["response"] = client.post(
            f"/v1/cases/{case_id}/analysis",
            headers={"Idempotency-Key": "slow-analysis"},
        )

    first_request = Thread(target=run_first_analysis)
    first_request.start()
    assert first_provider_call_started.wait(timeout=5)
    time.sleep(0.3)

    takeover = TestClient(app).post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "slow-analysis"},
    )

    release_first_provider_call.set()
    first_request.join(timeout=5)

    assert not first_request.is_alive()
    assert takeover.status_code == 409
    assert first_result["response"].status_code == 200
    assert provider.calls == 2


def test_invalid_provider_response_returns_recoverable_bad_gateway(tmp_path) -> None:
    class InvalidProvider:
        def analyze(self, request):
            raise ProviderResponseError("codex returned invalid screenshot evidence")

    client = TestClient(
        create_app(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'provider-error.db'}",
            storage_root=tmp_path / "images",
            vision_provider=InvalidProvider(),
            privacy_review_token="trusted-review",
        ),
        raise_server_exceptions=False,
    )
    case_id = client.post(
        "/v1/cases",
        json={"contract": "cf2609"},
    ).json()["case_id"]
    client.post(
        f"/v1/cases/{case_id}/images",
        headers={
            "Idempotency-Key": "image",
            "X-Privacy-Review-Token": "trusted-review",
        },
        data={
            "image_role": "STATE_DAILY",
            "role_confirmed": "true",
            "privacy_reviewed": "true",
        },
        files={"file": ("chart.png", b"\x89PNG\r\n\x1a\nfixture", "image/png")},
    ).raise_for_status()

    response = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "codex returned invalid screenshot evidence"


def test_analysis_heartbeat_stops_and_failed_claim_can_retry(
    monkeypatch,
    tmp_path,
) -> None:
    class FailOnceProvider:
        def __init__(self) -> None:
            self.calls = 0

        def analyze(self, request):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("provider failed")
            is_execution = "EXECUTION_60M" in (request.user_context or "")
            return ScreenshotEvidence(
                image_role="EXECUTION_60M" if is_execution else "STATE_DAILY",
                contract="rb2610",
                timeframe="60m" if is_execution else "1d",
                last_bar_closed=True,
                provider="fixture",
                model="fixture",
                prompt_version=request.prompt_version,
                image_sha256=f"fixture-{self.calls}",
            )

    monkeypatch.setattr(
        CaseRepository,
        "idempotency_lease",
        timedelta(milliseconds=120),
    )
    provider = FailOnceProvider()
    app = create_app(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'failure.db'}",
        storage_root=tmp_path / "images",
        vision_provider=provider,
        privacy_review_token="trusted-review",
    )
    client = TestClient(app, raise_server_exceptions=False)
    case_id = client.post(
        "/v1/cases",
        json={"contract": "rb2610"},
    ).json()["case_id"]
    for key, role in (("daily", "STATE_DAILY"), ("execution", "EXECUTION_60M")):
        client.post(
            f"/v1/cases/{case_id}/images",
            headers={
                "Idempotency-Key": key,
                "X-Privacy-Review-Token": "trusted-review",
            },
            data={
                "image_role": role,
                "role_confirmed": "true",
                "privacy_reviewed": "true",
            },
            files={
                "file": (
                    f"{key}.png",
                    b"\x89PNG\r\n\x1a\n" + key.encode(),
                    "image/png",
                )
            },
        ).raise_for_status()

    failed = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "retry-analysis"},
    )
    heartbeat_threads = [
        thread.name
        for thread in enumerate_threads()
        if thread.name.startswith("idempotency-heartbeat-")
    ]
    retried = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "retry-analysis"},
    )

    assert failed.status_code == 500
    assert heartbeat_threads == []
    assert retried.status_code == 200
    assert provider.calls == 3
