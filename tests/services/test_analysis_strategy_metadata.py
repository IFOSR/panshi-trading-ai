from trading_agent.domain.enums import EvidenceUsage
from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.services.analysis import build_analysis_payload
from trading_agent.workflows.analysis import AnalysisWorkflow


def test_analysis_payload_persists_the_selected_strategy_manifest() -> None:
    evidence = ScreenshotEvidence(
        image_role="STATE_DAILY",
        contract="rb2610",
        timeframe="1d",
        cutoff_time="2026-07-28T15:00:00+08:00",
        last_bar_closed=True,
        blocking_issues=[],
        allowed_usage=EvidenceUsage.EXACT,
        provider="fixture",
        model="fixture",
        prompt_version="chart-evidence-v2",
        image_sha256="fixture",
    )

    payload = build_analysis_payload(
        analysis_id="analysis-1",
        case_id="case-1",
        idempotency_key="analysis-key",
        case_state={
            "contract": "rb2610",
            "position": {"direction": "FLAT", "quantity": 0},
            "strategy": {
                "strategy_id": "structure_confirmation",
                "version": "1.0.0",
            },
        },
        evidence_set=[evidence],
        previous_analysis=None,
        workflow=AnalysisWorkflow(max_provider_attempts=1),
    )

    assert payload["strategy_manifest"]["strategy_id"] == "structure_confirmation"
    assert payload["strategy_manifest"]["display_name"] == "结构确认策略"
    assert payload["strategy_manifest"]["version"] == "1.0.0"
    assert payload["input_snapshot"]["case"] == {
        "contract": "rb2610",
        "position": {"direction": "FLAT", "quantity": 0},
        "risk": {},
        "strategy": {
            "strategy_id": "structure_confirmation",
            "version": "1.0.0",
        },
    }
    assert payload["input_snapshot"]["strategy_input"]["position"] == "FLAT"
    assert payload["input_snapshot"]["strategy_input"]["facts"]["contract"] == (
        "rb2610"
    )
