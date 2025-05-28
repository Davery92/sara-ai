import asyncio
import logging
import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from temporalio.client import Client as TemporalClient
from temporalio.worker import Worker
from workflows.dialogue_worker.workflows import ChatOrchestrationWorkflow
from workflows.dialogue_worker.activities import (
    enhance_prompt_activity,
    publish_to_nats_activity,
    save_artifact_activity,
    generate_chat_title_activity,
    update_chat_title_activity,
    extract_text_from_file_activity
)
from services.llm_proxy.app.activity import call_ollama_with_tool_support

async def main():
    logging.basicConfig(level=logging.INFO)
    temporal_server_address = os.getenv("TEMPORAL_URL", "temporal:7233")
    client = await TemporalClient.connect(temporal_server_address)
    task_queue_name = os.getenv("TEMPORAL_TASK_QUEUE", "dialogue-queue")

    worker = Worker(
        client,
        task_queue=task_queue_name,
        workflows=[
            ChatOrchestrationWorkflow
        ],
        activities=[
            enhance_prompt_activity,
            publish_to_nats_activity,
            save_artifact_activity,
            generate_chat_title_activity,
            update_chat_title_activity,
            extract_text_from_file_activity,
            call_ollama_with_tool_support
        ],
    )
    logging.info(f"Dialogue Worker (Temporal) started on task queue '{task_queue_name}'")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main()) 