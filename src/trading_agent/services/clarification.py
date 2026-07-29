from collections.abc import Mapping
import json
from typing import Any

from trading_agent.clarification.evidence import apply_confirmed_facts
from trading_agent.clarification.models import (
    ClarificationFact,
    ClarificationProposal,
    ClarificationQuestion,
)
from trading_agent.clarification.questions import questions_for_analysis
from trading_agent.domain.evidence import ScreenshotEvidence
from trading_agent.providers.base import ClarificationProvider, ClarificationRequest
from trading_agent.services.analysis import build_analysis_payload
from trading_agent.strategies.registry import StrategyNotFound
from trading_agent.workflows.analysis import AnalysisWorkflow


def _evidence_summary(analysis: Mapping[str, object]) -> str:
    summary = []
    raw_evidence = analysis.get("evidence_set", [])
    if isinstance(raw_evidence, list):
        for raw_item in raw_evidence:
            if not isinstance(raw_item, Mapping):
                continue
            summary.append(
                {
                    "image_role": raw_item.get("image_role"),
                    "instrument": raw_item.get("instrument"),
                    "contract": raw_item.get("contract"),
                    "timeframe": raw_item.get("timeframe"),
                    "cutoff_time": raw_item.get("cutoff_time"),
                    "last_bar_closed": raw_item.get("last_bar_closed"),
                    "open_interest_change": raw_item.get("open_interest_change"),
                    "strategy_facts": raw_item.get("strategy_facts"),
                    "blocking_issues": raw_item.get("blocking_issues"),
                    "allowed_usage": raw_item.get("allowed_usage"),
                }
            )
    return json.dumps(summary, ensure_ascii=False, separators=(",", ":"))[:8000]


def clarification_evidence_ids(
    evidence_set: list[ScreenshotEvidence],
) -> list[str]:
    return list(
        dict.fromkeys(
            observation.evidence_id
            for evidence in evidence_set
            for observation in evidence.observations
            if observation.provenance == "user_confirmed"
        )
    )


class ClarificationService:
    def __init__(
        self,
        provider: ClarificationProvider,
        *,
        workflow: AnalysisWorkflow | None = None,
    ) -> None:
        self.provider = provider
        self.workflow = workflow or AnalysisWorkflow()

    def questions(
        self,
        analysis: Mapping[str, object],
    ) -> list[ClarificationQuestion]:
        plugin = self._strategy_plugin(analysis)
        custom_questions = getattr(plugin, "clarification_questions", None)
        if callable(custom_questions):
            return list(custom_questions(analysis))
        return questions_for_analysis(analysis)

    def _strategy_plugin(self, analysis: Mapping[str, object]) -> object | None:
        manifest = analysis.get("strategy_manifest")
        if not isinstance(manifest, Mapping):
            return None
        strategy_id = manifest.get("strategy_id")
        version = manifest.get("version")
        if not isinstance(strategy_id, str) or not isinstance(version, str):
            return None
        try:
            return self.workflow.strategy_registry.resolve(strategy_id, version)
        except StrategyNotFound:
            return None

    def interpret(
        self,
        *,
        clarification_id: str,
        case_id: str,
        analysis: Mapping[str, object],
        message: str,
        questions: list[ClarificationQuestion],
    ) -> ClarificationProposal:
        return self.provider.interpret(
            ClarificationRequest(
                clarification_id=clarification_id,
                case_id=case_id,
                source_analysis_id=str(analysis["analysis_id"]),
                user_message=message,
                questions=questions,
                evidence_summary=_evidence_summary(analysis),
            )
        )

    def reevaluate(
        self,
        *,
        analysis_id: str,
        case_id: str,
        idempotency_key: str,
        case_state: Mapping[str, object],
        previous_analysis: dict[str, Any],
        proposal: Mapping[str, object],
    ) -> dict[str, Any]:
        evidence_set = [
            ScreenshotEvidence.model_validate(item)
            for item in previous_analysis.get("evidence_set", [])
        ]
        if not evidence_set:
            raise ValueError("latest analysis has no reusable evidence")
        raw_facts = proposal.get("facts", [])
        if not isinstance(raw_facts, list):
            raise ValueError("clarification proposal facts are invalid")
        facts = [
            ClarificationFact.model_validate(item)
            for item in raw_facts
        ]
        clarification_id = str(proposal["clarification_id"])
        plugin = self._strategy_plugin(previous_analysis)
        custom_merger = getattr(plugin, "apply_clarification_facts", None)
        merged = (
            list(
                custom_merger(
                    evidence_set,
                    facts,
                    clarification_id=clarification_id,
                )
            )
            if callable(custom_merger)
            else apply_confirmed_facts(
                evidence_set,
                facts,
                clarification_id=clarification_id,
            )
        )
        payload = build_analysis_payload(
            analysis_id=analysis_id,
            case_id=case_id,
            idempotency_key=idempotency_key,
            case_state=case_state,
            evidence_set=merged,
            previous_analysis=previous_analysis,
            workflow=self.workflow,
        )
        raw_previous_ids = previous_analysis.get("clarification_ids", [])
        previous_ids = raw_previous_ids if isinstance(raw_previous_ids, list) else []
        payload["clarification_ids"] = list(
            dict.fromkeys(
                [
                    *(str(item) for item in previous_ids),
                    clarification_id,
                ]
            )
        )
        payload["clarification_evidence_ids"] = clarification_evidence_ids(merged)
        return payload
