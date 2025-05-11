import os
import time
import uuid
from ..redis_utils import push_chat_chunk
from nats.aio.client import Client as NATS
import json
import socket

RAW_MEMORY_SUBJECT = os.getenv("RAW_MEMORY_SUBJECT", "memory.raw")
# Use localhost when running locally, and nats service name when in container
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222" if os.getenv("ENV") != "prod" else "nats://nats:4222")

async def save_chat_chunk(room_id: str, role: str, text: str):
    chunk = {
        "id": str(uuid.uuid4()),
        "room_id": room_id,
        "role": role,
        "text": text,
        "ts": time.time(),
    }
    # Save to Redis hot buffer
    await push_chat_chunk(room_id, chunk)
    # Publish to NATS for Postgres upsert
    nc = NATS()
    try:
        await nc.connect(servers=[NATS_URL])
        await nc.publish(RAW_MEMORY_SUBJECT, json.dumps(chunk).encode())
        await nc.drain()
    except Exception as e:
        print(f"Error connecting to NATS: {e}") 