import asyncio
from datetime import timedelta
import os

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker

from trading_agent.workflows.activities import AnalysisCommand, execute_analysis_command


TASK_QUEUE = "trading-analysis"


@activity.defn
async def persistable_analysis_activity(payload: dict[str, object]) -> dict[str, object]:
    command = AnalysisCommand.model_validate(payload)
    return await asyncio.to_thread(execute_analysis_command, command)


@workflow.defn
class DurableAnalysisWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, object]) -> dict[str, object]:
        return await workflow.execute_activity(
            persistable_analysis_activity,
            payload,
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )


async def run_worker() -> None:
    address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    delay = 1.0
    while True:
        try:
            client = await Client.connect(address)
            break
        except Exception:
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[DurableAnalysisWorkflow],
        activities=[persistable_analysis_activity],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
