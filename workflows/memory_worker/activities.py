# Add Python path setup at the top
import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from temporalio import activity
import json, uuid, importlib, os, httpx, logging
from typing import List, Dict, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("memory_worker")

# Use local redis client instead of gateway's
from redis_client import get_redis
from services.gateway.app.db.session import AsyncSessionLocal

# Import db_upsert directly
from services.common.db_upsert import upsert_memory

# LLM base URL for API calls
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434").rstrip("/")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "bge-m3")
SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "qwen3:32b")
API_TIMEOUT = float(os.environ.get("API_TIMEOUT", "30.0"))

@activity.defn
async def list_rooms_with_hot_buffer() -> list[str]:
    r = await get_redis()
    if not r:
        log.error("Failed to connect to Redis")
        return []
    keys = await r.keys("room:*:messages")
    return [k.split(":")[1] for k in keys]

@activity.defn
async def fetch_buffer(room_id: str) -> list[dict]:
    r = await get_redis()
    if not r:
        log.error("Failed to connect to Redis")
        return []
    raw = await r.lrange(f"room:{room_id}:messages", 0, -1)
    return [json.loads(x) for x in reversed(raw)]

@activity.defn
async def summarise_texts(chunks: list[dict]) -> str:
    text = "\n".join(c["text"] for c in chunks)
    try:
        # Call LLM summary endpoint
        return await call_llm_summary(text)
    except Exception as e:
        log.error(f"Error generating summary: {e}")
        # Return a simple concatenation as fallback
        return f"Conversation with {len(chunks)} messages."

async def call_llm_summary(text: str) -> str:
    """Call the LLM API to generate a summary of the provided text."""
    prompt = f"Summarize the following conversation in 2-3 sentences. Focus on key facts and decisions:\n\n{text}"
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{LLM_BASE_URL}/v1/chat/completions",
                json={
                    "model": SUMMARY_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant that summarizes conversations concisely."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 200
                },
                timeout=API_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
            summary = data["choices"][0]["message"]["content"].strip()
            log.info(f"Generated summary: {summary[:50]}...")
            return summary
    except (httpx.HTTPError, KeyError, IndexError) as e:
        log.error(f"Error in LLM summary call: {e}")
        raise

@activity.defn
async def embed_text(text: str) -> list[float]:
    """Get embedding from the LLM API for the provided text."""
    try:
        embedding = await get_embedding(text)
        log.info(f"Generated embedding vector of length {len(embedding)}")
        return embedding
    except Exception as e:
        log.error(f"Error generating embedding: {e}")
        raise

async def get_embedding(text: str) -> list[float]:
    """Call Ollama to get an embedding vector for the given text."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{LLM_BASE_URL}/v1/embeddings",
                json={"model": EMBEDDING_MODEL, "input": text},
                timeout=API_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json().get("data")
            if not data or "embedding" not in data[0]:
                raise ValueError("No embedding returned from API")
            return data[0]["embedding"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        log.error(f"Error in embedding generation: {e}")
        raise

@activity.defn
async def upsert_summary(room_id: str, summary: str, embedding: list[float]):
    try:
        async with AsyncSessionLocal() as session:
            await upsert_memory(
                session,
                mem_id=uuid.uuid4(),
                room_id=room_id,
                text=summary,
                embedding=embedding,
                msg_type="summary",
            )
            await session.commit()
            log.info(f"Saved summary for room {room_id}")
        
        # Clear the message buffer after successful save
        r = await get_redis()
        if r:
            await r.delete(f"room:{room_id}:messages")
            log.info(f"Cleared message buffer for room {room_id}")
        else:
            log.error("Failed to connect to Redis to clear message buffer")
    except Exception as e:
        log.error(f"Error upserting summary: {e}")
        raise

@activity.defn
async def process_rooms(room_ids: list[str]):
    """Process multiple rooms sequentially."""
    log.info(f"Processing {len(room_ids)} rooms")
    for room_id in room_ids:
        try:
            # Fetch buffer
            chunks = await fetch_buffer(room_id)
            if not chunks:
                log.info(f"No chunks found for room {room_id}")
                continue
            
            # Generate summary and embedding
            text = "\n".join(c["text"] for c in chunks)
            summary = await summarise_texts(chunks)
            embedding = await embed_text(text)
            
            # Upsert to database
            await upsert_summary(room_id, summary, embedding)
            log.info(f"Successfully processed room {room_id}")
        except Exception as e:
            log.error(f"Error processing room {room_id}: {e}")
