from trading_agent.domain.enums import MilestoneStatus
from trading_agent.strategy.context import StrategyContext
from trading_agent.strategy.evaluator import evaluate_strategy
from trading_agent.strategies.contracts import (
    StrategyInputSnapshot,
    StrategyManifest,
    StrategyRun,
    StrategySignal,
)


class StructureConfirmationStrategy:
    milestone_titles = {
        "DATA_VALIDITY": "数据有效性",
        "MARKET_STATE": "市场状态",
        "STRATEGY_PERMISSION": "策略许可",
        "PRICE_LOCATION": "价格位置",
        "POSITION_BEHAVIOR": "量仓行为",
        "MOMENTUM": "动量",
        "PRICE_CONFIRMATION": "价格确认",
    }
    manifest = StrategyManifest(
        strategy_id="structure_confirmation",
        display_name="结构确认策略",
        version="1.0.0",
        status="stable",
        entrypoint=(
            "trading_agent.strategies.structure_confirmation:"
            "StructureConfirmationStrategy"
        ),
        supported_markets=["CN_FUTURES"],
        supported_timeframes=["1d", "60m"],
        process_label="八步结构确认",
        risk_profile_id="china-futures-risk-v1",
    )

    def evaluate(self, snapshot: StrategyInputSnapshot) -> StrategyRun:
        context = StrategyContext.model_validate(
            {
                **snapshot.facts,
                "position": snapshot.position,
                **snapshot.risk_constraints,
            }
        )
        evaluation = evaluate_strategy(context)
        milestones = [
            step.model_copy(
                update={"title": self.milestone_titles.get(step.code, step.code)}
            )
            for step in evaluation.steps[:7]
        ]
        by_number = {step.number: step for step in milestones}
        permission = by_number[3]
        confirmation = by_number[7]
        blocking_steps = [
            step.number
            for step in milestones
            if step.status in {
                MilestoneStatus.BLOCKED,
                MilestoneStatus.INVALIDATED,
            }
        ]
        supporting_steps = [
            step.number
            for step in milestones
            if step.status == MilestoneStatus.CONFIRMED
        ]
        return StrategyRun(
            manifest=self.manifest,
            milestones=milestones,
            signal=StrategySignal(
                market_state=by_number[2].result,
                setup_code=(
                    permission.result if permission.result != "NONE" else None
                ),
                signal_stage=confirmation.result,
                data_valid=by_number[1].status == MilestoneStatus.CONFIRMED,
                price_confirmed=confirmation.status == MilestoneStatus.CONFIRMED,
                supporting_steps=supporting_steps,
                blocking_steps=blocking_steps,
                reason_codes=list(
                    dict.fromkeys(
                        blocker
                        for step in milestones
                        for blocker in step.blockers
                    )
                ),
                evidence_refs=list(
                    dict.fromkeys(
                        ref
                        for step in milestones
                        for ref in step.evidence_refs
                    )
                ),
                next_milestone=next(
                    (
                        condition
                        for step in milestones
                        for condition in step.next_conditions
                    ),
                    "等待下一次策略状态更新",
                ),
                upgrade_conditions=["数据有效、价格确认且风险通过"],
                invalidation_conditions=["结构失效或风险引擎否决"],
            ),
        )
