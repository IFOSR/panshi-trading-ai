from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from trading_agent.domain.enums import PositionDirection
from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.security.audit import build_analysis_audit
from trading_agent.services.change_report import build_change_report
from trading_agent.services.evidence_pipeline import primary_evidence
from trading_agent.strategy.context_builder import build_strategy_context
from trading_agent.workflows.analysis import AnalysisWorkflow


def build_analysis_payload(
    *,
    analysis_id: str,
    case_id: str,
    idempotency_key: str,
    case_state: Mapping[str, object],
    evidence_set: Sequence[ScreenshotEvidence],
    previous_analysis: dict[str, Any] | None,
    workflow: AnalysisWorkflow,
) -> dict[str, Any]:
    raw_position = cast_mapping(case_state.get("position")).get(
        "direction",
        PositionDirection.UNKNOWN.value,
    )
    try:
        position = PositionDirection(str(raw_position))
    except ValueError:
        position = PositionDirection.UNKNOWN
    context = build_strategy_context(
        evidence_set,
        case_contract=(
            str(case_state["contract"]) if case_state.get("contract") else None
        ),
        position=position,
        case_state=case_state,
        previous_evidence_set=(
            previous_analysis.get("evidence_set", [])
            if previous_analysis
            else []
        ),
    )
    serialized_evidence = [
        evidence.model_dump(mode="json") for evidence in evidence_set
    ]
    result = workflow.run(
        case_id,
        idempotency_key,
        context,
        lambda: {"evidence_set": serialized_evidence},
        strategy_id=(
            str(cast_mapping(case_state.get("strategy")).get("strategy_id"))
            if cast_mapping(case_state.get("strategy")).get("strategy_id")
            else None
        ),
        strategy_version=(
            str(cast_mapping(case_state.get("strategy")).get("version"))
            if cast_mapping(case_state.get("strategy")).get("version")
            else None
        ),
    )
    primary = primary_evidence(evidence_set)
    payload: dict[str, Any] = {
        "analysis_id": analysis_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_snapshot": {
            "case": {
                "contract": case_state.get("contract"),
                "position": dict(cast_mapping(case_state.get("position"))),
                "risk": dict(cast_mapping(case_state.get("risk"))),
                "strategy": dict(cast_mapping(case_state.get("strategy"))),
            },
            "strategy_input": {
                "facts": context.model_dump(mode="json"),
                "position": context.position.value,
                "risk_constraints": dict(
                    cast_mapping(case_state.get("risk"))
                ),
            },
        },
        "milestones": result.evaluation.model_dump(mode="json")["steps"],
        "decision": result.decision.model_dump(mode="json"),
        "rendered": result.rendered.model_dump(mode="json"),
        "evidence": primary.model_dump(mode="json"),
        "evidence_set": serialized_evidence,
        "strategy_manifest": result.strategy_manifest.model_dump(mode="json"),
        "audit": build_analysis_audit(
            list(evidence_set),
            result.evaluation.steps,
            strategy_id=result.strategy_manifest.strategy_id,
            strategy_version=result.strategy_manifest.version,
        ).model_dump(mode="json"),
    }
    payload["change_report"] = build_change_report(previous_analysis, payload)
    return payload


def cast_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}
