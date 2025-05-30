from temporalio import activity
import json, uuid
from redis.asyncio import Redis
from services.gateway.app.redis_client import get_redis
from services.gateway.app.db.session import async_session
from services.common.db_upsert import upsert_memory

@activity.defn
async def list_rooms_with_hot_buffer() -> list[str]:
    r: Redis = await get_redis()
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
    # TODO: call your Ollama/qwen2.5 summary endpoint
    return await call_llm_summary(text)

@activity.defn
async def embed_text(text: str) -> list[float]:
    # TODO: reuse your existing embedding client
    return await get_embedding(text)

@activity.defn
async def upsert_summary(room_id: str, summary: str, embedding: list[float]):
    async with async_session() as session:
        await upsert_memory(
            session,
            mem_id=uuid.uuid4(),
            room_id=room_id,
            text=summary,
            embedding=embedding,
            msg_type="summary",
        )
        await session.commit()
    r = await get_redis()
    await r.delete(f"room:{room_id}:messages")
