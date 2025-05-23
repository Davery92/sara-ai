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

# ─── Ollama endpoint & NATS subject helpers ────────────────────────────────────
LLM_BASE_URL = os.environ["LLM_BASE_URL"].rstrip("/")
from services.common.nats_helpers import session_subjects
# use session_subjects.reply for `chat.reply.*` pattern
# ────────────────────────────────────────────────────────────────────────────────

async def handle_message(msg):
    """Callback: receive NATS msg, embed, and write to Postgres."""
    data = msg.data.decode()
    payload = json.loads(data)
    msg_id = payload["id"]
    text   = payload["text"]

    # 1) fetch embedding from Ollama
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{LLM_BASE_URL}/v1/embeddings",
            json={"model": "bge-m3", "input": text},
        )
        resp.raise_for_status()
        embedding = resp.json()["data"][0]["embedding"]

    # 2) write to Postgres
        # 2) write to Postgres
    # Ensure the table exists on first run
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        session.add(EmbeddingMessage(text=text, embedding=embedding)) # <-- CHANGE THIS LINE
        await session.commit()

    print(f"Persisted embedding for message {msg_id}")

async def run_worker():
    # 1) connect to NATS
    nc = NATS()
    await nc.connect(servers=[os.environ.get("NATS_URL", "nats://127.0.0.1:4222")])

    # 2) derive the reply subject string
    # session_subjects() returns (session_id, request_subject, reply_subject)
    _, _, reply_subject = session_subjects()

    # 3) subscribe to that reply subject
    await nc.subscribe(reply_subject, cb=handle_message)
    print(f"Subscribed to reply subject: {reply_subject}")

    # 4) keep the service alive
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run_worker())
