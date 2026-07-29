from trading_agent.strategy.context import StrategyContext
from trading_agent.domain.enums import ActionType, MilestoneStatus, PositionDirection
from trading_agent.domain.milestone import MilestoneResult
from trading_agent.strategies.contracts import (
    StrategyInputSnapshot,
    StrategyManifest,
    StrategyRun,
    StrategySignal,
)
from trading_agent.strategies.registry import StrategyRegistry
from trading_agent.workflows.analysis import AnalysisWorkflow


def test_workflow_is_idempotent_and_retries_only_provider_activity() -> None:
    calls = 0

    def extract() -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("provider timeout")
        return {"provider": "codex"}

    workflow = AnalysisWorkflow(max_provider_attempts=2)
    context = StrategyContext(contract="rb2610", timeframe="1d", state_bar_closed=False)

    first = workflow.run("case-1", "key-1", context, extract)

    assert calls == 2
    assert len(first.evaluation.steps) == 8
    assert first.evaluation.steps[7].status == MilestoneStatus.BLOCKED
    assert 8 in first.decision.blocking_steps


def test_workflow_recomputes_when_a_failed_persistence_attempt_is_retried() -> None:
    workflow = AnalysisWorkflow(max_provider_attempts=1)
    blocked = StrategyContext(
        contract="rb2610",
        timeframe="1d",
        state_bar_closed=False,
    )
    approved = StrategyContext(
        contract="rb2610",
        timeframe="1d",
        state_bar_closed=True,
        data_cutoff_time="2026-07-20",
        data_age_seconds=0,
        max_data_age_seconds=129_600,
        trend_score=-3,
        price_location="BELOW_BOLL_MID_ABOVE_LOWER",
        open_interest_change=100,
        momentum_state="BEARISH_STRENGTHENING",
        price_confirmation=True,
        price_confirmation_direction="BEARISH",
        price_confirmation_type="PULLBACK",
        position=PositionDirection.FLAT,
        account_risk_limit=0.01,
        proposed_risk=0.005,
    )

    first = workflow.run(
        "case-1",
        "retry-after-persistence-failure",
        blocked,
        lambda: {"attempt": 1},
    )
    retried = workflow.run(
        "case-1",
        "retry-after-persistence-failure",
        approved,
        lambda: {"attempt": 2},
    )

    assert first.decision.action == ActionType.WAIT_FOR_SETUP
    assert retried.decision.action == ActionType.ENTER_CONDITIONAL
    assert retried.provider_evidence == {"attempt": 2}


def test_workflow_uses_context_risk_inputs_to_approve_entry() -> None:
    context = StrategyContext(
        contract="rb2610",
        timeframe="1d",
        state_bar_closed=True,
        data_cutoff_time="2026-07-20",
        data_age_seconds=0,
        max_data_age_seconds=129_600,
        prior_market_state="T-",
        trend_score=-3,
        price_location="BELOW_BOLL_MID_ABOVE_LOWER",
        open_interest_change=100,
        momentum_state="BEARISH_STRENGTHENING",
        price_confirmation=True,
        price_confirmation_direction="BEARISH",
        price_confirmation_type="PULLBACK",
        position=PositionDirection.FLAT,
        account_risk_limit=0.01,
        proposed_risk=0.005,
    )

    result = AnalysisWorkflow(max_provider_attempts=1).run(
        "case-1",
        "approved-risk",
        context,
        lambda: {"provider": "codex"},
    )

    assert result.evaluation.steps[7].status == MilestoneStatus.CONFIRMED
    assert result.decision.action == ActionType.ENTER_CONDITIONAL
    assert "PRICE_NOT_CONFIRMED" not in result.decision.reason_codes


def test_workflow_exits_an_invalidated_open_position() -> None:
    context = StrategyContext(
        contract="rb2610",
        timeframe="1d",
        state_bar_closed=True,
        data_cutoff_time="2026-07-20",
        data_age_seconds=0,
        max_data_age_seconds=129_600,
        prior_market_state="T-",
        trend_score=-3,
        price_location="BELOW_BOLL_LOWER",
        open_interest_change=100,
        momentum_state="BEARISH_STRENGTHENING",
        price_confirmation=True,
        price_confirmation_direction="BEARISH",
        price_confirmation_type="PULLBACK",
        position=PositionDirection.LONG,
        account_risk_limit=0.01,
        proposed_risk=0.005,
        position_invalidated=True,
    )

    result = AnalysisWorkflow(max_provider_attempts=1).run(
        "case-1",
        "invalidated-position",
        context,
        lambda: {"provider": "codex"},
    )

    assert result.decision.action == ActionType.EXIT


def test_forced_exit_realigns_next_milestone_after_step_eight_is_confirmed() -> None:
    context = StrategyContext(
        contract="rb2610",
        timeframe="1d",
        state_bar_closed=True,
        data_cutoff_time="2026-07-20",
        data_age_seconds=0,
        trend_score=-3,
        price_location="BELOW_BOLL_LOWER",
        open_interest_change=100,
        momentum_state="BEARISH_STRENGTHENING",
        price_confirmation=True,
        price_confirmation_direction="BEARISH",
        price_confirmation_type="BREAKOUT",
        position=PositionDirection.LONG,
        position_invalidated=True,
    )

    result = AnalysisWorkflow(max_provider_attempts=1).run(
        "case-1",
        "forced-exit-without-risk-inputs",
        context,
        lambda: {"provider": "codex"},
    )

    assert result.decision.action == ActionType.EXIT
    assert result.evaluation.steps[7].status == MilestoneStatus.CONFIRMED
    assert result.decision.blocking_steps == []
    assert result.decision.next_milestone == "等待下一次策略状态更新"


def test_final_action_is_the_step_eight_result() -> None:
    context = StrategyContext(
        contract="rb2610",
        timeframe="1d",
        state_bar_closed=True,
        data_cutoff_time="2026-07-20",
        data_age_seconds=0,
        max_data_age_seconds=129_600,
        trend_score=-3,
        price_location="BELOW_BOLL_MID_ABOVE_LOWER",
        open_interest_change=100,
        momentum_state="BEARISH_STRENGTHENING",
        price_confirmation=True,
        price_confirmation_direction="BEARISH",
        price_confirmation_type="PULLBACK",
        position=PositionDirection.FLAT,
        account_risk_limit=0.01,
        proposed_risk=0.005,
    )

    result = AnalysisWorkflow(max_provider_attempts=1).run(
        "case-1",
        "aligned-step-eight",
        context,
        lambda: {"provider": "codex"},
    )

    assert result.decision.action == ActionType.ENTER_CONDITIONAL
    assert result.evaluation.steps[7].result == ActionType.ENTER_CONDITIONAL
    assert result.evaluation.steps[7].status == MilestoneStatus.CONFIRMED
    assert 8 in result.decision.supporting_steps
    assert 8 not in result.decision.blocking_steps


def test_unknown_position_branches_are_evaluated_independently() -> None:
    context = StrategyContext(
        contract="rb2610",
        timeframe="1d",
        state_bar_closed=True,
        data_cutoff_time="2026-07-20",
        data_age_seconds=0,
        max_data_age_seconds=129_600,
        trend_score=-3,
        price_location="BELOW_BOLL_MID_ABOVE_LOWER",
        open_interest_change=100,
        momentum_state="BEARISH_STRENGTHENING",
        price_confirmation=True,
        price_confirmation_direction="BEARISH",
        price_confirmation_type="PULLBACK",
        position=PositionDirection.UNKNOWN,
        account_risk_limit=0.01,
        proposed_risk=0.005,
    )

    result = AnalysisWorkflow(max_provider_attempts=1).run(
        "case-1",
        "position-branches",
        context,
        lambda: {"provider": "codex"},
    )
    actions = {
        branch.scope: branch.action
        for branch in result.rendered.position_branches
    }

    assert actions[PositionDirection.FLAT] == ActionType.ENTER_CONDITIONAL
    assert actions[PositionDirection.LONG] == ActionType.EXIT
    assert actions[PositionDirection.SHORT] == ActionType.HOLD


def test_add_requires_step_seven_to_confirm_the_same_strategy() -> None:
    context = StrategyContext(
        contract="rb2610",
        timeframe="1d",
        state_bar_closed=True,
        data_cutoff_time="2026-07-20",
        data_age_seconds=0,
        trend_score=-3,
        price_location="BELOW_BOLL_LOWER",
        price_confirmation=True,
        price_confirmation_direction="BULLISH",
        price_confirmation_type="BREAKOUT",
        position=PositionDirection.SHORT,
        account_risk_limit=0.01,
        proposed_risk=0.005,
        add_confirmation=True,
    )

    result = AnalysisWorkflow(max_provider_attempts=1).run(
        "case-1",
        "mismatched-add",
        context,
        lambda: {"provider": "codex"},
    )

    assert result.evaluation.steps[6].status == MilestoneStatus.CANDIDATE
    assert result.decision.action == ActionType.HOLD


class ThreeStepStrategy:
    manifest = StrategyManifest(
        strategy_id="three_step",
        display_name="三步测试策略",
        version="2.0.0",
        status="test",
        entrypoint="tests:ThreeStepStrategy",
        supported_markets=["CN_FUTURES"],
        supported_timeframes=["1d"],
        process_label="三步信号确认",
        risk_profile_id="china-futures-risk-v1",
    )

    def evaluate(self, snapshot: StrategyInputSnapshot) -> StrategyRun:
        assert snapshot.facts["contract"] == "rb2610"
        milestones = [
            MilestoneResult(
                number=1,
                code="INPUT",
                status=MilestoneStatus.CONFIRMED,
                result="VALID",
            ),
            MilestoneResult(
                number=2,
                code="SETUP",
                status=MilestoneStatus.CONFIRMED,
                result="THREE_STEP_LONG",
            ),
            MilestoneResult(
                number=3,
                code="CONFIRMATION",
                status=MilestoneStatus.CONFIRMED,
                result="TRIGGERED",
            ),
        ]
        return StrategyRun(
            manifest=self.manifest,
            milestones=milestones,
            signal=StrategySignal(
                market_state="T+",
                setup_code="THREE_STEP_LONG",
                signal_stage="TRIGGERED",
                data_valid=True,
                price_confirmed=True,
                supporting_steps=[1, 2, 3],
                evidence_refs=[],
                next_milestone="等待下一次策略状态更新",
                upgrade_conditions=["保持三步确认"],
                invalidation_conditions=["三步结构失效"],
            ),
        )


def test_workflow_uses_registry_strategy_and_dynamic_action_step() -> None:
    registry = StrategyRegistry(default_strategy_id="three_step")
    registry.register(ThreeStepStrategy())
    workflow = AnalysisWorkflow(
        max_provider_attempts=1,
        strategy_registry=registry,
    )
    context = StrategyContext(
        contract="rb2610",
        timeframe="1d",
        state_bar_closed=True,
        data_cutoff_time="2026-07-28T15:00:00+08:00",
        data_age_seconds=0,
        position=PositionDirection.FLAT,
        account_risk_limit=0.01,
        proposed_risk=0.005,
    )

    result = workflow.run(
        "case-1",
        "three-step",
        context,
        lambda: {"provider": "fixture"},
        strategy_id="three_step",
        strategy_version="2.0.0",
    )

    assert result.strategy_manifest.strategy_id == "three_step"
    assert result.strategy_manifest.version == "2.0.0"
    assert len(result.evaluation.steps) == 4
    assert result.evaluation.steps[-1].number == 4
    assert result.evaluation.steps[-1].result == ActionType.ENTER_CONDITIONAL
    assert result.decision.action == ActionType.ENTER_CONDITIONAL
    assert result.decision.supporting_steps == [1, 2, 3, 4]


def test_hold_is_candidate_when_strategy_milestones_are_blocked() -> None:
    context = StrategyContext(
        contract="rb2610",
        timeframe="1d",
        state_bar_closed=True,
        data_cutoff_time="2026-07-20",
        data_age_seconds=0,
        trend_score=-1,
        position=PositionDirection.LONG,
        account_risk_limit=0.01,
        proposed_risk=0.005,
    )

    result = AnalysisWorkflow(max_provider_attempts=1).run(
        "case-1",
        "candidate-hold",
        context,
        lambda: {"provider": "codex"},
    )

    assert result.decision.action == ActionType.HOLD
    assert result.evaluation.steps[7].status == MilestoneStatus.CANDIDATE
    assert result.evaluation.steps[7].details["risk_status"] == "APPROVED"
    assert "MARKET_STATE_UNKNOWN" not in result.decision.reason_codes
    assert {4, 5, 6, 7} <= set(result.decision.blocking_steps)
    assert 3 not in result.decision.blocking_steps


def test_entry_is_blocked_when_position_behavior_or_momentum_is_blocked() -> None:
    context = StrategyContext(
        contract="rb2610",
        timeframe="1d",
        state_bar_closed=True,
        data_cutoff_time="2026-07-20",
        data_age_seconds=0,
        trend_score=-3,
        price_location="BELOW_BOLL_MID_ABOVE_LOWER",
        open_interest_change=None,
        volume_state="UNKNOWN",
        position_behavior_state="UNKNOWN",
        momentum_state="UNKNOWN",
        price_confirmation=True,
        price_confirmation_direction="BEARISH",
        price_confirmation_type="PULLBACK",
        position=PositionDirection.FLAT,
        account_risk_limit=0.01,
        proposed_risk=0.005,
    )

    result = AnalysisWorkflow(max_provider_attempts=1).run(
        "case-1",
        "blocked-position-momentum",
        context,
        lambda: {"provider": "codex"},
    )

    assert result.decision.action == ActionType.WAIT_FOR_SETUP
    assert result.evaluation.steps[7].status == MilestoneStatus.BLOCKED
    assert {5, 6, 8} <= set(result.decision.blocking_steps)
