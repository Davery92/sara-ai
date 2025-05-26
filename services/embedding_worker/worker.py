import os
import sys
import json
import asyncio
from dotenv import load_dotenv

# ─── Make project root importable ───────────────────────────────────────────────
repo_root = os.path.abspath(os.path.join(__file__, "..", "..", ".."))
sys.path.insert(0, repo_root)
# ────────────────────────────────────────────────────────────────────────────────

# ─── Load .env ─────────────────────────────────────────────────────────────────
load_dotenv(os.path.join(repo_root, ".env"))
# ────────────────────────────────────────────────────────────────────────────────

# ─── SQLAlchemy + pgvector imports ─────────────────────────────────────────────
# ─── SQLAlchemy + pgvector imports ─────────────────────────────────────────────
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
# your Gateway's models:
# Try different import paths based on environment
try:
    # First try direct imports (for Docker)
    from app.db.models import EmbeddingMessage, Base # <-- CHANGE THIS LINE
except ImportError:
    try:
        # Then try local project structure (for development)
        from services.gateway.app.db.models import EmbeddingMessage, Base # <-- CHANGE THIS LINE
    except ImportError:
        # Dynamic import as last resort
        import importlib
        gateway_models = importlib.import_module("app.db.models")
        EmbeddingMessage = gateway_models.EmbeddingMessage # <-- CHANGE THIS LINE
        Base = gateway_models.Base
# ────────────────────────────────────────────────────────────────────────────────
# ────────────────────────────────────────────────────────────────────────────────

# ─── NATS + HTTP client imports ────────────────────────────────────────────────
from nats.aio.client import Client as NATS
import httpx
# ────────────────────────────────────────────────────────────────────────────────

# ─── Ollama endpoint & NATS subject helpers ────────────────────────────────────
LLM_BASE_URL = os.environ["LLM_BASE_URL"].rstrip("/")
# IMPORTANT: Use the RAW_MEMORY_SUBJECT from environment or default
RAW_MEMORY_SUBJECT = os.getenv("RAW_MEMORY_SUBJECT", "memory.raw")
# ────────────────────────────────────────────────────────────────────────────────

# ─── Build Async DB engine & session factory ──────────────────────────────────
DATABASE_URL = (
    f"postgresql+asyncpg://{os.environ['POSTGRES_USER']}:"
    f"{os.environ['POSTGRES_PASSWORD']}@"
    f"{os.environ['POSTGRES_HOST']}:"
    f"{os.environ['POSTGRES_PORT']}/"
    f"{os.environ['POSTGRES_DB']}"
)
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)
# ────────────────────────────────────────────────────────────────────────────────

async def handle_message(msg):
    """Callback: receive NATS msg, embed, and write to Postgres."""
    data = msg.data.decode()
    payload = json.loads(data)
    
    # Ensure payload contains 'id' and 'text' as expected from RAW_MEMORY_SUBJECT chunks
    msg_id = payload.get("id")
    text   = payload.get("text")
    if not msg_id or not text:
        print(f"Skipping message due to missing ID or text: {payload}")
        return # Or log error more severely
    
    # 1) fetch embedding from Ollama
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{LLM_BASE_URL}/v1/embeddings",
            json={"model": os.getenv("EMBEDDING_MODEL", "bge-m3"), "input": text}, # Use ENV for embedding model
        )
        resp.raise_for_status()
        embedding = resp.json()["data"][0]["embedding"]

    # 2) write to Postgres
    # async with engine.begin() as conn: # Removed original line
    # await conn.run_sync(Base.metadata.create_all) # Ensure table exists if not already # Removed original line
    # The following two lines are kept from the original context, assuming `engine` and `AsyncSessionLocal` are defined elsewhere
    # and `Base.metadata.create_all` is handled appropriately (e.g., by Alembic migrations or initial app setup).
    # If `engine` and `AsyncSessionLocal` are indeed defined in the `... (existing code) ...` part, this is fine.
    # However, the original `Proposed Change` in the user query didn't show where `engine` and `AsyncSessionLocal` are defined.
    # For now, I will keep the structure close to the user's `Proposed Change`.
    # It's assumed `Base.metadata.create_all` is managed outside this worker's `handle_message`.

    async with AsyncSessionLocal() as session:
        # Use EmbeddingMessage directly for storage, assuming room_id is chat_id
        # The payload from RAW_MEMORY_SUBJECT should contain 'room_id'
        room_id = payload.get("room_id")
        if not room_id:
            print(f"Skipping save: room_id missing in payload for msg {msg_id}")
            return
        
        session.add(EmbeddingMessage(id=msg_id, room_id=room_id, content=text, embedding=embedding))
        await session.commit()

    print(f"Persisted embedding for message {msg_id} in room {room_id}")

async def run_worker():
    # 1) connect to NATS
    nc = NATS()
    await nc.connect(servers=[os.environ.get("NATS_URL", "nats://127.0.0.1:4222")])

    # 2) subscribe to the RAW_MEMORY_SUBJECT
    await nc.subscribe(RAW_MEMORY_SUBJECT, cb=handle_message)
    print(f"Subscribed to embedding subject: {RAW_MEMORY_SUBJECT}")

    # 3) keep the service alive
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run_worker())
