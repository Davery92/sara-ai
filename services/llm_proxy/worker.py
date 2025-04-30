import asyncio
import logging
from temporalio.client import Client as TemporalClient
from temporalio.worker import Worker
from app.workflows import ChatWorkflow
from app.activity import call_ollama

async def main():
    logging.basicConfig(level=logging.INFO)
    client = await TemporalClient.connect("temporal:7233")
    worker = Worker(
        client,
        task_queue="llm-queue",
        workflows=[ChatWorkflow],
        activities=[call_ollama],
    )
    logging.info("LLM Worker started on 'llm-queue'")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(main())