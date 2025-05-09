# Add Python path setup at the top
import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pgvector.sqlalchemy
from temporalio.client import Client
from temporalio.worker import Worker
from workflow import MemoryRollupWorkflow
import activities as acts
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError

async def main():
    client = await Client.connect("temporal:7233")

    # ✅ Try starting the workflow, tolerate if already running
    try:
        await client.start_workflow(
            MemoryRollupWorkflow.run,
            id="memory-rollup-cron",
            task_queue="memory-rollup",
            cron_schedule="*/30 * * * *",
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE
        )
        print("✅ Started memory-rollup-cron workflow")
    except WorkflowAlreadyStartedError:
        print("⚠️ Workflow 'memory-rollup-cron' is already running — skipping start")

    await Worker(
        client,
        task_queue="memory-rollup",
        workflows=[MemoryRollupWorkflow],
        activities=[
            acts.list_rooms_with_hot_buffer,
            acts.fetch_buffer,
            acts.summarise_texts,
            acts.embed_text,
            acts.upsert_summary,
        ],
    ).run()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
