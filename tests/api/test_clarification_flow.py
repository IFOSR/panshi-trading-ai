from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from trading_agent.api.app import create_app
from trading_agent.clarification.models import (
    ClarificationFact,
    ClarificationProposal,
)
from trading_agent.domain.enums import EvidenceUsage
from trading_agent.domain.evidence import (
    Evidence,
    FactSupport,
    ScreenshotEvidence,
    StrategyEvidenceFacts,
)
from trading_agent.market.bars import MarketBar
from trading_agent.market.resolver import MarketDataSnapshot
from trading_agent.providers.base import (
    ProviderResponseError,
    ProviderUnavailable,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


class CountingVisionProvider:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, request) -> ScreenshotEvidence:
        self.calls += 1
        is_execution = "EXECUTION_60M" in (request.user_context or "")
        cutoff = datetime.now(SHANGHAI) - timedelta(
            minutes=30 if is_execution else 60
        )
        if is_execution:
            return ScreenshotEvidence(
                image_role="EXECUTION_60M",
                contract="CF2609",
                timeframe="60m",
                cutoff_time=cutoff.isoformat(),
                last_bar_closed=None,
                blocking_issues=[
                    "截图未明确标注最后一根60分钟K线是否已经收盘。"
                ],
                allowed_usage=EvidenceUsage.QUALITATIVE_ONLY,
                provider="codex",
                model="gpt-5.6-sol",
                prompt_version=request.prompt_version,
                image_sha256="execution-hash",
            )
        observations = [
            Evidence(
                evidence_id="daily-trend",
                kind="trend_bias",
                value="BEARISH",
                confidence=0.95,
                provenance="multimodal_model",
            ),
            Evidence(
                evidence_id="daily-location",
                kind="price_location",
                value="BELOW_BOLL_MID_ABOVE_LOWER",
                confidence=0.95,
                provenance="multimodal_model",
            ),
            Evidence(
                evidence_id="daily-momentum",
                kind="momentum_state",
                value="BEARISH_STRENGTHENING",
                confidence=0.95,
                provenance="multimodal_model",
            ),
        ]
        return ScreenshotEvidence(
            image_role="STATE_DAILY",
            contract="CF2609",
            timeframe="1d",
            cutoff_time=cutoff.isoformat(),
            last_bar_closed=None,
            observations=observations,
            strategy_facts=StrategyEvidenceFacts(
                trend_bias="BEARISH",
                price_location="BELOW_BOLL_MID_ABOVE_LOWER",
                momentum_state="BEARISH_STRENGTHENING",
            ),
            strategy_fact_support={
                "trend_bias": FactSupport(
                    confidence=0.95,
                    evidence_refs=["daily-trend"],
                ),
                "price_location": FactSupport(
                    confidence=0.95,
                    evidence_refs=["daily-location"],
                ),
                "momentum_state": FactSupport(
                    confidence=0.95,
                    evidence_refs=["daily-momentum"],
                ),
            },
            blocking_issues=[
                "BAR_CLOSE_UNKNOWN",
                "CCYD末端柱体未显示可可靠读取的数值或明确分类标签，无法确认当前持仓行为。",
            ],
            allowed_usage=EvidenceUsage.QUALITATIVE_ONLY,
            provider="codex",
            model="gpt-5.6-sol",
            prompt_version=request.prompt_version,
            image_sha256="daily-hash",
        )


class CompleteClarificationProvider:
    def __init__(self) -> None:
        self.calls = 0

    def interpret(self, request) -> ClarificationProposal:
        self.calls += 1
        questions = {question.field: question for question in request.questions}

        def fact(field, value, *, question_field=None):
            question = questions[question_field or field]
            return ClarificationFact(
                question_id=question.question_id,
                field=field,
                value=value,
                explanation=f"用户明确补充 {field}。",
                resolves_blockers=question.blocking_issues,
            )

        facts = [
            fact("state_bar_closed", True),
            fact("execution_bar_closed", True),
            fact("position_behavior_state", "POSITION_LIQUIDATION"),
            fact("open_interest_change", -4425),
            fact("price_confirmation", True),
            fact(
                "price_confirmation_direction",
                "BEARISH",
                question_field="price_confirmation",
            ),
            fact(
                "price_confirmation_type",
                "PULLBACK",
                question_field="price_confirmation",
            ),
        ]
        return ClarificationProposal(
            clarification_id=request.clarification_id,
            source_analysis_id=request.source_analysis_id,
            user_message=request.user_message,
            facts=facts,
            unresolved_question_ids=[],
            interpretation=(
                "我理解为：日线和 60 分钟 K 线均已收盘，"
                "持仓量减少 4425，持仓行为为减仓，形成向下回踩确认。"
            ),
            provider="codex",
            model="gpt-5.6-sol",
        )


class RefreshingMarketDataResolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, case_state, evidence):
        self.calls += 1
        if self.calls <= 2:
            return None
        timeframe = "60m" if evidence.image_role == "EXECUTION_60M" else "1d"
        cutoff = datetime.now(SHANGHAI) - timedelta(minutes=30)
        spacing = timedelta(hours=1) if timeframe == "60m" else timedelta(days=1)
        bars = [
            MarketBar(
                contract="CF2609",
                timeframe=timeframe,
                timestamp=cutoff - spacing * (21 - index),
                trading_date=(cutoff - spacing * (21 - index)).date(),
                open=100 + index,
                high=102 + index,
                low=99 + index,
                close=101 + index,
                volume=1000 + index,
                open_interest=5000 + index * 10,
                is_closed=True,
                source="fixture",
            )
            for index in range(22)
        ]
        return MarketDataSnapshot(
            contract="CF2609",
            timeframe=timeframe,
            cutoff_time=bars[-1].timestamp,
            last_bar_closed=True,
            price_axis_verified=True,
            rollover_active=False,
            near_price_limit=False,
            sources=["fixture"],
            bars=bars,
        )


def prepared_client(
    tmp_path,
    *,
    clarification_provider=None,
    market_data_resolver=None,
) -> tuple[TestClient, str, CountingVisionProvider, dict]:
    vision_provider = CountingVisionProvider()
    client = TestClient(
        create_app(
            database_url=f"sqlite+pysqlite:///{tmp_path / 'clarification.db'}",
            storage_root=tmp_path / "images",
            vision_provider=vision_provider,
            clarification_provider=(
                clarification_provider or CompleteClarificationProvider()
            ),
            market_data_resolver=market_data_resolver,
            privacy_review_token="trusted-review",
        ),
        raise_server_exceptions=False,
    )
    case_id = client.post(
        "/v1/cases",
        json={"instrument": "CF", "contract": "CF2609"},
    ).json()["case_id"]
    for key, role in (("daily", "STATE_DAILY"), ("execution", "EXECUTION_60M")):
        response = client.post(
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
        )
        response.raise_for_status()
    analysis = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis-initial"},
    )
    analysis.raise_for_status()
    return client, case_id, vision_provider, analysis.json()


def test_get_clarifications_returns_only_concrete_open_questions(tmp_path) -> None:
    client, case_id, _, analysis = prepared_client(tmp_path)

    response = client.get(f"/v1/cases/{case_id}/clarifications")

    assert response.status_code == 200
    assert response.json()["source_analysis_id"] == analysis["analysis_id"]
    assert [item["field"] for item in response.json()["questions"]] == [
        "state_bar_closed",
        "execution_bar_closed",
        "position_behavior_state",
        "open_interest_change",
        "price_confirmation",
    ]
    assert response.json()["history"] == []


def test_message_refreshes_evidence_before_creating_idempotent_pending_proposal(
    tmp_path,
) -> None:
    provider = CompleteClarificationProvider()
    client, case_id, vision, analysis = prepared_client(
        tmp_path,
        clarification_provider=provider,
    )
    message = {
        "message": (
            "日线和 60 分钟都收盘了，CCYD 显示减仓 4425，"
            "已形成向下回踩确认。"
        )
    }

    first = client.post(
        f"/v1/cases/{case_id}/clarifications",
        headers={"Idempotency-Key": "clarification-message-1"},
        json=message,
    )
    repeated = client.post(
        f"/v1/cases/{case_id}/clarifications",
        headers={"Idempotency-Key": "clarification-message-1"},
        json=message,
    )

    assert first.status_code == 200
    assert repeated.json() == first.json()
    assert first.json()["status"] == "PENDING_CONFIRMATION"
    assert first.json()["source_analysis_id"] != analysis["analysis_id"]
    assert first.json()["interpretation"].startswith("我理解为")
    assert provider.calls == 1
    assert vision.calls == 4
    assert len(client.get(f"/v1/cases/{case_id}/analyses").json()) == 2


def test_message_refreshes_automatic_evidence_before_asking_user(tmp_path) -> None:
    provider = CompleteClarificationProvider()
    resolver = RefreshingMarketDataResolver()
    client, case_id, vision, initial = prepared_client(
        tmp_path,
        clarification_provider=provider,
        market_data_resolver=resolver,
    )

    response = client.post(
        f"/v1/cases/{case_id}/clarifications",
        headers={"Idempotency-Key": "clarification-auto-refresh"},
        json={
            "message": (
                "请直接从公开行情和截图确认收盘状态、持仓量变化和价格结构。"
            )
        },
    )
    repeated = client.post(
        f"/v1/cases/{case_id}/clarifications",
        headers={"Idempotency-Key": "clarification-auto-refresh"},
        json={
            "message": (
                "请直接从公开行情和截图确认收盘状态、持仓量变化和价格结构。"
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert repeated.status_code == 200
    assert repeated.json() == payload
    assert payload["status"] == "AUTO_RESOLVED"
    assert payload["source_analysis_id"] == initial["analysis_id"]
    assert payload["result_analysis_id"] != initial["analysis_id"]
    assert provider.calls == 0
    assert vision.calls == 4
    assert len(client.get(f"/v1/cases/{case_id}/analyses").json()) == 2
    questions = client.get(f"/v1/cases/{case_id}/clarifications").json()
    assert questions["source_analysis_id"] == payload["result_analysis_id"]
    assert questions["questions"] == []


def test_message_can_refresh_an_analysis_without_user_questions(tmp_path) -> None:
    provider = CompleteClarificationProvider()
    resolver = RefreshingMarketDataResolver()
    client, case_id, vision, _ = prepared_client(
        tmp_path,
        clarification_provider=provider,
        market_data_resolver=resolver,
    )
    resolved = client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis-resolved-before-refresh"},
    )
    resolved.raise_for_status()
    assert client.get(
        f"/v1/cases/{case_id}/clarifications"
    ).json()["questions"] == []

    response = client.post(
        f"/v1/cases/{case_id}/clarifications",
        headers={"Idempotency-Key": "automatic-refresh-without-questions"},
        json={"message": "请重新读取截图并刷新公开行情。"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "AUTO_RESOLVED"
    assert response.json()["source_analysis_id"] == resolved.json()["analysis_id"]
    assert provider.calls == 0
    assert vision.calls == 4


def test_confirm_reuses_evidence_and_creates_auditable_aligned_analysis(
    tmp_path,
) -> None:
    client, case_id, vision, initial = prepared_client(tmp_path)
    proposal = client.post(
        f"/v1/cases/{case_id}/clarifications",
        headers={"Idempotency-Key": "clarification-message-1"},
        json={"message": "日线和 60 分钟均已收盘，其余信息如问题所述。"},
    )
    proposal.raise_for_status()
    clarification_id = proposal.json()["clarification_id"]

    confirmed = client.post(
        f"/v1/cases/{case_id}/clarifications/{clarification_id}/confirm",
        headers={"Idempotency-Key": "clarification-confirm-1"},
    )
    repeated = client.post(
        f"/v1/cases/{case_id}/clarifications/{clarification_id}/confirm",
        headers={"Idempotency-Key": "clarification-confirm-1"},
    )

    assert confirmed.status_code == 200
    payload = confirmed.json()
    assert repeated.json()["analysis_id"] == payload["analysis_id"]
    assert payload["analysis_id"] != initial["analysis_id"]
    assert vision.calls == 4
    assert payload["clarification_ids"] == [clarification_id]
    assert all(
        evidence_id.startswith(f"user-confirmed-{clarification_id}-")
        for evidence_id in payload["clarification_evidence_ids"]
    )
    confirmed_observations = [
        observation
        for evidence in payload["evidence_set"]
        for observation in evidence["observations"]
        if observation["provenance"] == "user_confirmed"
    ]
    assert len(confirmed_observations) == 7
    milestone_by_number = {
        item["number"]: item for item in payload["milestones"]
    }
    assert any(
        ref.startswith(f"user-confirmed-{clarification_id}-")
        for ref in milestone_by_number[5]["evidence_refs"]
    )
    assert any(
        ref.startswith(f"user-confirmed-{clarification_id}-")
        for ref in milestone_by_number[7]["evidence_refs"]
    )
    assert payload["decision"]["action"] == milestone_by_number[8]["result"]
    history = client.get(f"/v1/cases/{case_id}/clarifications").json()["history"]
    assert history[-1]["status"] == "CONFIRMED"
    assert history[-1]["result_analysis_id"] == payload["analysis_id"]


def test_stale_proposal_is_rejected_without_calling_vision_again(tmp_path) -> None:
    client, case_id, vision, _ = prepared_client(tmp_path)
    proposal = client.post(
        f"/v1/cases/{case_id}/clarifications",
        headers={"Idempotency-Key": "clarification-message-1"},
        json={"message": "日线已收盘。"},
    )
    proposal.raise_for_status()
    client.post(
        f"/v1/cases/{case_id}/analysis",
        headers={"Idempotency-Key": "analysis-newer"},
    ).raise_for_status()
    calls_before_confirm = vision.calls

    response = client.post(
        (
            f"/v1/cases/{case_id}/clarifications/"
            f"{proposal.json()['clarification_id']}/confirm"
        ),
        headers={"Idempotency-Key": "clarification-confirm-stale"},
    )

    assert response.status_code == 409
    assert "latest analysis" in response.json()["detail"]
    assert vision.calls == calls_before_confirm


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (ProviderResponseError("invalid clarification"), 502),
        (ProviderUnavailable("codex unavailable"), 503),
    ],
)
def test_clarification_provider_errors_are_recoverable(
    tmp_path,
    error,
    expected_status,
) -> None:
    class FailingClarificationProvider:
        def interpret(self, request):
            raise error

    client, case_id, _, _ = prepared_client(
        tmp_path,
        clarification_provider=FailingClarificationProvider(),
    )

    response = client.post(
        f"/v1/cases/{case_id}/clarifications",
        headers={"Idempotency-Key": "clarification-message-failed"},
        json={"message": "日线已收盘。"},
    )

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)
