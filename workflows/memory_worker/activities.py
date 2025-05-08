from temporalio import activity
import json, uuid, importlib, os, httpx, logging
from typing import List, Dict, Any, Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("memory_worker")

# Try different import paths based on environment
try:
    # First try direct imports (for Docker)
    from app.redis_client import get_redis
    from app.db.session import AsyncSessionLocal
except ImportError:
    # Then try local project structure (for development)
    from services.gateway.app.redis_client import get_redis
    from services.gateway.app.db.session import AsyncSessionLocal

# Import db_upsert with the same approach
try:
    from common.db_upsert import upsert_memory
except ImportError:
    try:
        from services.common.db_upsert import upsert_memory
    except ImportError:
        # Dynamic import as last resort
        common_module = importlib.import_module("services.common.db_upsert")
        upsert_memory = common_module.upsert_memory

# LLM base URL for API calls
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434").rstrip("/")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "bge-m3")
SUMMARY_MODEL = os.environ.get("SUMMARY_MODEL", "qwen2.5-0.5b")
API_TIMEOUT = float(os.environ.get("API_TIMEOUT", "30.0"))

@activity.defn
async def list_rooms_with_hot_buffer() -> list[str]:
    r = await get_redis()
    keys = await r.keys("room:*:messages")
    return [k.decode().split(":")[1] for k in keys]

@activity.defn
async def fetch_buffer(room_id: str) -> list[dict]:
    r = await get_redis()
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
        await r.delete(f"room:{room_id}:messages")
        log.info(f"Cleared message buffer for room {room_id}")
    except Exception as e:
        log.error(f"Error upserting summary: {e}")
        raise
