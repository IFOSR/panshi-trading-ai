from trading_agent.strategy.context import StrategyContext
from trading_agent.domain.enums import MilestoneStatus
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
    repeated = workflow.run("case-1", "key-1", context, extract)

    assert first == repeated
    assert calls == 2
    assert len(first.evaluation.steps) == 8
    assert first.evaluation.steps[7].status == MilestoneStatus.BLOCKED
    assert 8 in first.decision.blocking_steps
