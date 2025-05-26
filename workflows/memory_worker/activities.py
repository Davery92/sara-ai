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
# from services.gateway.app.db.session import AsyncSessionLocal # Moved into upsert_summary

# Import db_upsert directly
# from services.common.db_upsert import upsert_memory # Moved into upsert_summary

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
    
    # Pattern to find all unified user memory streams
    all_keys = await r.keys("user:*:messages") 
    
    user_ids = set() # Store unique user IDs
    for k in all_keys:
        # Example key: "user:9a601ac0-...:messages"
        # Ensure k is a string before splitting
        key_str = k.decode('utf-8') if isinstance(k, bytes) else str(k)
        parts = key_str.split(':')
        if len(parts) == 3 and parts[0] == 'user' and parts[2] == 'messages':
            user_id = parts[1] # Extract the user_id part
            user_ids.add(user_id)
        else:
            log.warning(f"Unexpected Redis key format found: {key_str}. Skipping this key.")
    
    log.info(f"Redis unified user memory keys found: {all_keys}") # all_keys might be bytes
    log.info(f"Extracted unique user_ids to process: {list(user_ids)}")
    
    return list(user_ids) # Return as a list of user_ids

@activity.defn
async def fetch_buffer(user_id: str) -> list[dict]:
    r = await get_redis()
    if not r:
        log.error("Failed to connect to Redis")
        return []
    
    key = f"user:{user_id}:messages" # Unified key
    log.info(f"Fetching unified buffer from Redis. Key: {key}")
    raw = await r.lrange(key, 0, -1)
    # When summarizing, we might want to discard the 'user_id' and 'room_id' fields
    # from the chunks, or keep them if the summarizer uses them.
    # For now, just return raw chunks as they are, but the summarizer will see the fields.
    return [json.loads(x) for x in reversed(raw)] # x will be bytes if decode_responses=False for redis client

@activity.defn
async def summarise_texts(chunks: list[dict]) -> str:
    text = "\n".join(c["text"] for c in chunks)
    try:
        # Call LLM summary endpoint
        response = await call_llm_summary(text)
        return response
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
    # Import database-related modules inside the function
    from services.gateway.app.db.session import AsyncSessionLocal
    from services.common.db_upsert import upsert_memory
    
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
            # THIS KEY IS WRONG FOR UNIFIED MEMORY - needs to be user:{user_id}:messages
            # This function upsert_summary takes room_id, not user_id.
            # This deletion logic needs to be in process_rooms where user_id is available.
            # await r.delete(f"room:{room_id}:messages") 
            # log.info(f"Cleared message buffer for room {room_id}")
            pass # Deletion will be handled in process_rooms
        else:
            log.error("Failed to connect to Redis to clear message buffer")
    except Exception as e:
        log.error(f"Error upserting summary: {e}")
        raise

@activity.defn
async def process_rooms(user_ids_to_process: list[str]):
    log.info(f"Processing {len(user_ids_to_process)} unified user memory streams")
    for user_id in user_ids_to_process: # Iterate directly over user_ids
        try:
            # Fetch buffer (now expects only user_id)
            chunks = await fetch_buffer(user_id) 
            if not chunks:
                log.info(f"No chunks found for unified memory for user {user_id}")
                continue
            
            # Generate summary and embedding
            # Ensure all chunks have 'text' field. If not, provide a default or skip.
            texts_to_join = []
            for c_idx, c in enumerate(chunks):
                if "text" not in c or c["text"] is None:
                    log.warning(f"Chunk {c_idx} for user {user_id} is missing 'text' field or it is None. Chunk: {str(c)[:100]}")
                    texts_to_join.append("") # Add empty string to avoid error, or handle as per requirement
                else:
                    texts_to_join.append(str(c["text"])) # Ensure text is string
            text = "\n".join(texts_to_join)
            
            # Pass chunks directly to summarizer, it expects list[dict]
            summary = await summarise_texts(chunks) 
            embedding = await embed_text(text) # embed_text expects concatenated string
            
            # Upsert to database. 
            # The `memory` table needs a `user_id` column and the `room_id` might be redundant or a foreign key to a chat.
            # ASSUMPTION: For now, we will use the *first* room_id found in the chunks
            # as the `room_id` for the `memory` table entry if available, otherwise user_id.
            # This implies `upsert_summary` might need user_id if `memory` table is changed to use user_id as primary key.
            
            first_chunk_room_id = chunks[0].get("room_id")
            if not first_chunk_room_id:
                log.warning(f"No 'room_id' found in the first chunk for user {user_id}. Using user_id as fallback for memory record.")
                # Consider a more robust way to handle this if room_id is critical for `memory` table structure.
                # For now, using user_id as the identifier for upsert_summary if no room_id is found.
                # This means `upsert_summary`'s `room_id` parameter will effectively store `user_id` in this case.
                # This might require changes in `upsert_summary` or the DB schema if `room_id` has specific constraints.
                first_chunk_room_id = user_id 
            else:
                # Ensure it's a string, as room_id from chunk could be UUID object or other types
                first_chunk_room_id = str(first_chunk_room_id)

            # The `upsert_summary` function still expects a `room_id`.
            # For unified memory, this `room_id` field in the `memory` table might now store the user_id,
            # or a specific identifier indicating it's a user-level summary if the table schema is not changed.
            # If the `memory` table is altered to have a `user_id` column, `upsert_summary` needs modification.
            # For now, we pass `first_chunk_room_id` (which could be a room_id or user_id as fallback)
            await upsert_summary(first_chunk_room_id, summary, embedding)
            log.info(f"Successfully upserted unified summary for user {user_id} (using identifier {first_chunk_room_id} for memory table)")

            # Clear the unified message buffer after successful save
            r_del = await get_redis()
            if r_del:
                unified_key_to_delete = f"user:{user_id}:messages"
                await r_del.delete(unified_key_to_delete)
                log.info(f"Cleared unified message buffer for user {user_id} (key: {unified_key_to_delete})")
            else:
                log.error(f"Failed to connect to Redis to clear unified message buffer for user {user_id}")
        except Exception as e:
            log.error(f"Error processing unified memory for user {user_id}: {e}", exc_info=True)
