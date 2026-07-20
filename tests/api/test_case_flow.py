from fastapi.testclient import TestClient

from trading_agent.api.app import create_app
from trading_agent.domain.enums import EvidenceUsage
from trading_agent.domain.evidence import ScreenshotEvidence


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
        headers={"Idempotency-Key": "image-1"},
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


def test_default_app_reads_database_url_from_environment(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'configured.db'}"
    monkeypatch.setenv("TRADING_AGENT_DATABASE_URL", database_url)

    app = create_app()

    assert app.state.database_url == database_url
