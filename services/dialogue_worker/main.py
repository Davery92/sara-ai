import asyncio
import os
import aiohttp
import json
from datetime import timedelta
from typing import AsyncIterator
from temporalio import workflow, activity
from temporalio.client import Client
from temporalio.worker import Worker
from nats.aio.client import Client as NATS
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get Ollama URL from environment variable
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://100.104.68.115:11434")

@activity.defn
async def call_ollama(model: str, prompt: str) -> dict:
    """Call Ollama API for LLM completion"""
    try:
        url = f"{OLLAMA_URL}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama error: {response.status} - {error_text}")
                
                result = await response.json()
                logger.info(f"Ollama response: {result}")
                return result
    
    except Exception as e:
        logger.error(f"Error calling Ollama: {e}")
        raise

@workflow.defn
class LLMWorkflow:
    @workflow.run
    async def run(self, model: str, prompt: str, stream: bool = False) -> dict:
        # For now, we'll just use the non-streaming version
        # Temporal doesn't handle streaming activities well
        return await workflow.execute_activity(
            call_ollama,
            args=[model, prompt],
            start_to_close_timeout=timedelta(seconds=30)
        )

async def main():
    # connect to NATS (optional: to subscribe to requests)
    nc = NATS()
    await nc.connect(servers=["nats://nats:4222"])
    
    # connect to Temporal
    client = await Client.connect("temporal:7233")
    
    # run the worker
    async with Worker(
        client,
        task_queue="llm-queue",
        workflows=[LLMWorkflow],
        activities=[call_ollama]
    ):
        logger.info("Worker listening on 'llm-queue'...")
        await asyncio.Future()  # run forever

if __name__ == "__main__":
    asyncio.run(main())