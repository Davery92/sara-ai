# services/gateway/app/db/session.py
import os
from dotenv import load_dotenv, find_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .models import Base

# Load the nearest .env file (walks up directories)
load_dotenv(find_dotenv())

# Build the DB URL (or use DATABASE_URL from .env if present)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://"
    f"{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}"
    f"@{os.getenv('POSTGRES_HOST', 'postgres')}:{os.getenv('POSTGRES_PORT', '5432')}/{os.getenv('POSTGRES_DB')}"
)

# Create the async engine & session factory
engine = create_async_engine(DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# On startup, ensure pgvector is enabled and tables exist
async def init_models():
    async with engine.begin() as conn:
        # 1) Create the pgvector extension if missing
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        # 2) Create all tables
        await conn.run_sync(Base.metadata.create_all)

# FastAPI dependency to get an AsyncSession
async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session