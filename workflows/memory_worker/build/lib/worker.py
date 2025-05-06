from temporalio.client import Client
from temporalio.worker import Worker
from .workflow import MemoryRollupWorkflow
import workflows.memory_worker.activities as acts

async def main():
    client = await Client.connect("temporal:7233")

    # start the cron workflow (idempotent if it exists)
    await client.start_workflow(
        MemoryRollupWorkflow.run,
        id="memory-rollup-cron",
        task_queue="memory-rollup",
        cron_schedule="*/30 * * * *",
    )

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
