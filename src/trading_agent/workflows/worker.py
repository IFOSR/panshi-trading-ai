import asyncio
from datetime import timedelta
import os
from typing import Any

from temporalio import workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker


TASK_QUEUE = "trading-analysis"


@workflow.defn
class DurableAnalysisWorkflow:
    @workflow.run
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        loaded = await workflow.execute_activity(
            "load_analysis",
            payload,
            result_type=dict[str, Any],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )
        if loaded.get("cached_result"):
            return dict(loaded["cached_result"])
        try:
            renewed = await workflow.execute_activity(
                "renew_analysis",
                loaded,
                result_type=dict[str, Any],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            extracted = await workflow.execute_activity(
                "extract_evidence",
                renewed,
                result_type=dict[str, Any],
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=RetryPolicy(maximum_attempts=2),
            )
            renewed = await workflow.execute_activity(
                "renew_analysis",
                extracted,
                result_type=dict[str, Any],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            merged = await workflow.execute_activity(
                "merge_market_data",
                renewed,
                result_type=dict[str, Any],
                start_to_close_timeout=timedelta(minutes=1),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            renewed = await workflow.execute_activity(
                "renew_analysis",
                merged,
                result_type=dict[str, Any],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            evaluated = await workflow.execute_activity(
                "evaluate_strategy",
                renewed,
                result_type=dict[str, Any],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
            renewed = await workflow.execute_activity(
                "renew_analysis",
                evaluated,
                result_type=dict[str, Any],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            return await workflow.execute_activity(
                "persist_analysis",
                renewed,
                result_type=dict[str, Any],
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
        except Exception:
            await workflow.execute_activity(
                "fail_analysis",
                loaded,
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            raise


async def run_worker() -> None:
    from trading_agent.market.resolver import configured_market_data_resolver
    from trading_agent.workflows.activities import AnalysisActivities

    address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    delay = 1.0
    while True:
        try:
            client = await Client.connect(address)
            break
        except Exception:
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
    activities = AnalysisActivities(
        market_data_resolver=configured_market_data_resolver(),
    )
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[DurableAnalysisWorkflow],
        activities=[
            activities.load_analysis,
            activities.renew_analysis,
            activities.extract_evidence,
            activities.merge_market_data,
            activities.evaluate_strategy,
            activities.persist_analysis,
            activities.fail_analysis,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
