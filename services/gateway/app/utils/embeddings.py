import os
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Use .get() with a default value instead of direct access
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434").rstrip("/")

async def compute_embedding(text: str) -> list[float]:
    """Call Ollama to get an embedding vector for the given text."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{LLM_BASE_URL}/v1/embeddings",
            json={"model": "bge-m3", "input": text},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json().get("data")
        if not data or "embedding" not in data[0]:
            raise ValueError("No embedding returned")
        return data[0]["embedding"]