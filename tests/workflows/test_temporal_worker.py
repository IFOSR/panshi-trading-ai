from trading_agent.workflows.worker import TASK_QUEUE, DurableAnalysisWorkflow


def test_temporal_worker_registers_named_workflow_and_queue() -> None:
    assert TASK_QUEUE == "trading-analysis"
    assert DurableAnalysisWorkflow.__name__ == "DurableAnalysisWorkflow"
