from collections.abc import Callable

from pydantic import BaseModel

from trading_agent.decision.policy import DecisionInput, decide_action
from trading_agent.domain.decision import ActionDecision
from trading_agent.domain.enums import MilestoneStatus
from trading_agent.domain.milestone import StrategyEvaluation
from trading_agent.rendering.models import RenderedDecision
from trading_agent.rendering.service import render_decision
from trading_agent.risk.engine import evaluate_risk
from trading_agent.risk.models import RiskContext
from trading_agent.strategy.context import StrategyContext
from trading_agent.strategy.evaluator import evaluate_strategy


class WorkflowResult(BaseModel):
    evaluation: StrategyEvaluation
    decision: ActionDecision
    rendered: RenderedDecision
    provider_evidence: dict[str, object]


class AnalysisWorkflow:
    def __init__(self, max_provider_attempts: int = 2) -> None:
        self.max_provider_attempts = max_provider_attempts
        self._results: dict[tuple[str, str], WorkflowResult] = {}

    def run(
        self,
        case_id: str,
        idempotency_key: str,
        context: StrategyContext,
        extract: Callable[[], dict[str, object]],
    ) -> WorkflowResult:
        cache_key = (case_id, idempotency_key)
        if cache_key in self._results:
            return self._results[cache_key]
        for attempt in range(self.max_provider_attempts):
            try:
                evidence = extract()
                break
            except TimeoutError:
                if attempt + 1 == self.max_provider_attempts:
                    raise
        evaluation = evaluate_strategy(context)
        risk = evaluate_risk(RiskContext(
            state_bar_closed=context.state_bar_closed,
            account_risk_limit=None,
            proposed_risk=None,
        ))
        risk_step = evaluation.steps[7].model_copy(update={
            "status": (
                MilestoneStatus.CONFIRMED
                if risk.status == "APPROVED"
                else MilestoneStatus.BLOCKED
            ),
            "result": risk.status,
            "blockers": risk.reason_codes,
            "next_conditions": (
                [] if risk.status == "APPROVED" else ["补齐风险参数并重新评估"]
            ),
        })
        evaluation = StrategyEvaluation(steps=[*evaluation.steps[:7], risk_step])
        decision = decide_action(DecisionInput(
            evaluation=evaluation, context=context, risk=risk
        ))
        result = WorkflowResult(
            evaluation=evaluation,
            decision=decision,
            rendered=render_decision(decision),
            provider_evidence=evidence,
        )
        self._results[cache_key] = result
        return result
