from trading_agent.workflows.activities import AnalysisCommand
from trading_agent.workflows.worker import TASK_QUEUE, DurableAnalysisWorkflow


def test_temporal_worker_registers_named_workflow_and_queue() -> None:
    assert TASK_QUEUE == "trading-analysis"
    assert DurableAnalysisWorkflow.__name__ == "DurableAnalysisWorkflow"


def test_temporal_command_does_not_serialize_database_credentials() -> None:
    command = AnalysisCommand(
        case_id="case-1",
        idempotency_key="key-1",
        storage_root="/app/data/images",
    )

    assert "database" not in command.model_dump_json().lower()
