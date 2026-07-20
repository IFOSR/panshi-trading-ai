from datetime import datetime, timedelta, timezone
from pathlib import Path

from trading_agent.security.audit import AnalysisAudit, build_model_trace
from trading_agent.security.retention import RetainedAnalysis, expire_raw_image


def test_raw_image_expires_but_replay_metadata_remains(tmp_path: Path) -> None:
    image = tmp_path / "chart.png"
    image.write_bytes(b"original")
    retained = RetainedAnalysis(
        image_path=image,
        image_sha256="hash",
        created_at=datetime.now(timezone.utc) - timedelta(days=31),
        retention_days=30,
        evidence={"contract": "rb2610"},
        decision={"action": "WAIT_FOR_DATA"},
    )

    result = expire_raw_image(retained, now=datetime.now(timezone.utc))

    assert result.raw_image_deleted is True
    assert not image.exists()
    assert result.evidence["contract"] == "rb2610"
    assert result.decision["action"] == "WAIT_FOR_DATA"


def test_model_trace_never_contains_account_identifier() -> None:
    trace = build_model_trace(
        prompt_version="chart-v1",
        model="gpt-5.6-sol",
        user_context="账户 12345678，分析 rb2610",
        sensitive_values=["12345678"],
    )

    assert "12345678" not in str(trace)


def test_analysis_audit_requires_all_replay_versions() -> None:
    audit = AnalysisAudit(
        model_version="gpt-5.6-sol",
        prompt_version="chart-v1",
        strategy_version="strategy-v1",
        risk_version="risk-v1",
        rule_versions=["DQ-001", "MS-001", "RK-001"],
    )

    assert audit.rule_versions
