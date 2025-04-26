"""Very thin helper that POSTs to Ollama’s `/api/chat` and yields tokens."""
import os
from typing import AsyncIterator
import httpx

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

async def stream_completion(payload: dict) -> AsyncIterator[dict]:
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=payload) as resp:
            async for line in resp.aiter_lines():
                if line.strip():
                    yield {"delta": line}