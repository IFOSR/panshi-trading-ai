from collections.abc import Callable

from pydantic import BaseModel

from trading_agent.decision.policy import (
    StrategyDecisionInput,
    decide_action_from_strategy,
)
from trading_agent.domain.decision import ActionDecision
from trading_agent.domain.enums import ActionType, MilestoneStatus, PositionDirection
from trading_agent.domain.milestone import MilestoneResult, StrategyEvaluation
from trading_agent.rendering.models import RenderedDecision
from trading_agent.rendering.service import render_decision
from trading_agent.risk.engine import evaluate_risk
from trading_agent.risk.models import RiskContext
from trading_agent.strategy.context import StrategyContext
from trading_agent.strategies.contracts import (
    StrategyInputSnapshot,
    StrategyManifest,
)
from trading_agent.strategies.registry import (
    StrategyRegistry,
    configured_strategy_registry,
)


class WorkflowResult(BaseModel):
    evaluation: StrategyEvaluation
    decision: ActionDecision
    rendered: RenderedDecision
    provider_evidence: dict[str, object]
    strategy_manifest: StrategyManifest


class AnalysisWorkflow:
    def __init__(
        self,
        max_provider_attempts: int = 2,
        strategy_registry: StrategyRegistry | None = None,
    ) -> None:
        self.max_provider_attempts = max_provider_attempts
        self.strategy_registry = (
            strategy_registry or configured_strategy_registry()
        )

    def run(
        self,
        case_id: str,
        idempotency_key: str,
        context: StrategyContext,
        extract: Callable[[], dict[str, object]],
        *,
        strategy_id: str | None = None,
        strategy_version: str | None = None,
    ) -> WorkflowResult:
        for attempt in range(self.max_provider_attempts):
            try:
                evidence = extract()
                break
            except TimeoutError:
                if attempt + 1 == self.max_provider_attempts:
                    raise
        plugin = (
            self.strategy_registry.resolve(strategy_id, strategy_version)
            if strategy_id
            else self.strategy_registry.default()
        )
        strategy_run = plugin.evaluate(
            StrategyInputSnapshot(
                facts=context.model_dump(mode="json"),
                position=context.position.value,
            )
        )
        evaluation = StrategyEvaluation(steps=strategy_run.milestones)
        risk = evaluate_risk(RiskContext(
            state_bar_closed=context.state_bar_closed,
            contract_mismatch=context.contract_mismatch,
            rollover_active=context.rollover_active,
            near_price_limit=context.near_price_limit,
            stop_distance_ratio=context.stop_distance_ratio,
            max_stop_distance_ratio=context.max_stop_distance_ratio,
            account_risk_limit=context.account_risk_limit,
            proposed_risk=context.proposed_risk,
            correlated_exposure_exceeded=context.correlated_exposure_exceeded,
            market_state_known=(
                strategy_run.signal.market_state != "U"
                and strategy_run.signal.data_valid
            ),
        ))
        action_step_number = len(evaluation.steps) + 1
        decision = decide_action_from_strategy(StrategyDecisionInput(
            signal=strategy_run.signal,
            context=context,
            risk=risk,
            action_step_number=action_step_number,
            forced_exit=context.forced_exit,
            position_invalidated=context.position_invalidated,
            reduce_required=context.reduce_required,
            add_confirmation=context.add_confirmation,
        ))
        action_status = (
            MilestoneStatus.BLOCKED
            if decision.action in {ActionType.WAIT_FOR_DATA, ActionType.WAIT_FOR_SETUP}
            else MilestoneStatus.CANDIDATE
            if (
                decision.action == ActionType.WATCH_ENTRY
                or (
                    decision.action == ActionType.HOLD
                    and bool(decision.blocking_steps)
                )
            )
            else MilestoneStatus.CONFIRMED
        )
        action_step = MilestoneResult(
            number=action_step_number,
            code="RISK_AND_ACTION",
            title="风险与动作",
            status=action_status,
            result=decision.action.value,
            rule_ids=["RK-001"],
            evidence_refs=decision.evidence_refs,
            blockers=decision.reason_codes if action_status == MilestoneStatus.BLOCKED else [],
            next_conditions=(
                [decision.next_milestone]
                if decision.next_milestone and action_status != MilestoneStatus.CONFIRMED
                else []
            ),
            details={
                "risk_status": risk.status,
                "action": decision.action.value,
                "position_scope": decision.position_scope.value,
            },
        )
        evaluation = StrategyEvaluation(steps=[*evaluation.steps, action_step])
        supporting = [
            step
            for step in decision.supporting_steps
            if step != action_step_number
        ]
        blocking = [
            step
            for step in decision.blocking_steps
            if step != action_step_number
        ]
        if action_status == MilestoneStatus.CONFIRMED:
            supporting.append(action_step_number)
        else:
            blocking.append(action_step_number)
        decision = ActionDecision.model_validate(
            {
                **decision.model_dump(mode="json"),
                "supporting_steps": sorted(set(supporting)),
                "blocking_steps": sorted(set(blocking)),
                "next_milestone": (
                    strategy_run.signal.next_milestone
                    if blocking
                    else "等待下一次策略状态更新"
                ),
            }
        )
        branch_decisions: dict[PositionDirection, ActionDecision] | None = None
        if context.position == PositionDirection.UNKNOWN:
            branch_decisions = {}
            for scope in (
                PositionDirection.FLAT,
                PositionDirection.LONG,
                PositionDirection.SHORT,
            ):
                branch_context = context.model_copy(
                    update={
                        "position": scope,
                    }
                )
                branch_decisions[scope] = decide_action_from_strategy(
                    StrategyDecisionInput(
                        signal=strategy_run.signal,
                        context=branch_context,
                        risk=risk,
                        action_step_number=action_step_number,
                        forced_exit=False,
                        position_invalidated=(
                            (scope == PositionDirection.LONG and context.trend_score <= -2)
                            or (
                                scope == PositionDirection.SHORT
                                and context.trend_score >= 2
                            )
                        ),
                        reduce_required=context.reduce_required,
                        add_confirmation=False,
                    )
                )
        result = WorkflowResult(
            evaluation=evaluation,
            decision=decision,
            rendered=render_decision(decision, branch_decisions),
            provider_evidence=evidence,
            strategy_manifest=strategy_run.manifest,
        )
        return result
