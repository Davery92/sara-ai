import asyncio
import logging
from temporalio.client import Client as TemporalClient
from temporalio.worker import Worker
from app.activity import call_ollama, call_ollama_with_tool_support
import sys
from pathlib import Path
import os

async def main():
    logging.basicConfig(level=logging.INFO)
    temporal_server_address = os.getenv("TEMPORAL_URL", "temporal:7233")
    client = await TemporalClient.connect(temporal_server_address)
    task_queue_name = os.getenv("TEMPORAL_TASK_QUEUE", "llm-queue")

    worker = Worker(
        client,
        task_queue=task_queue_name,
        workflows=[
            # ChatOrchestrationWorkflow handled by dialogue_temporal_worker
        ],
        activities=[
            call_ollama,
            call_ollama_with_tool_support,
            # extract_text_from_file_activity handled by dialogue_temporal_worker
        ],
    )
    logging.info(f"LLM Worker (Temporal) started on task queue '{task_queue_name}'")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())