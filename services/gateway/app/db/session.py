# services/gateway/app/db/session.py
import os
from dotenv import load_dotenv, find_dotenv
from sqlalchemy import text, inspect, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncConnection
from sqlalchemy.orm import sessionmaker
from .models import Base
import pgvector.asyncpg
import asyncpg

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
# FIX: Remove the 'connect_args' dictionary from create_async_engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
)

AsyncSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession
)

# CRITICAL FIX: Custom Asyncpg Adapter for pgvector registration
# This creates a custom connection adapter that specifically registers pgvector
# on the raw asyncpg connection *before* SQLAlchemy fully wraps it.
# This pattern is sometimes seen when standard hooks are insufficient.
class CustomAsyncpgConnection(AsyncConnection):
    async def __aenter__(self):
        # When the connection context is entered, register pgvector
        raw_conn = await self.get_raw_connection()
        try:
            # Check if it's actually an asyncpg.Connection before calling run_sync
            if isinstance(raw_conn, asyncpg.Connection):
                await pgvector.asyncpg.register_vector(raw_conn)
                print("DEBUG: pgvector.asyncpg.register_vector successful on raw asyncpg.Connection.")
            else:
                # If it's not the raw asyncpg.Connection, something is still wrong with SQLAlchemy's internal passing
                print(f"WARNING: _do_register_vector_type received unexpected connection type: {type(raw_conn)}")
                # Fallback to run_sync if it's SQLAlchemy's adapter object
                await raw_conn.run_sync(pgvector.asyncpg.register_vector)
                print("DEBUG: pgvector.asyncpg.register_vector run_sync successful on adapter.")
        except Exception as e:
            print(f"ERROR: Failed to register pgvector types in custom adapter: {e}")
            # This is critical, re-raise to see the stack trace
            raise
        return await super().__aenter__()

# Replace the default connection class for asyncpg dialect
# This ensures that whenever SQLAlchemy creates a connection via asyncpg,
# it uses our custom class which handles pgvector registration.
from sqlalchemy.dialects import postgresql as pg_dialect # Import as different name to avoid conflict
pg_dialect.dialect.connection_cls = CustomAsyncpgConnection # <-- Inject custom connection class

# On startup, ensure pgvector is enabled and tables exist
async def init_models():
    """
    Initializes database models and extensions.
    This function should be explicitly awaited during FastAPI startup (lifespan event).
    """
    print("DEBUG: init_models() starting. Attempting to connect to DB and create extensions/tables.")
    async with engine.begin() as conn:
        # 1) Create the pgvector extension if missing
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        print("DEBUG: pgvector extension checked/created.")
        
        # 2) Check if tables exist and create them if needed
        def tables_exist_sync(sync_conn):
            inspector = inspect(sync_conn)
            return 'users' in inspector.get_table_names() or 'memory' in inspector.get_table_names()

        tables_exist = await conn.run_sync(tables_exist_sync)

        if not tables_exist:
            print(f"DEBUG: No key tables found. Creating all tables via Base.metadata.create_all.")
            await conn.run_sync(Base.metadata.create_all)
            print("DEBUG: All tables created successfully.")
        else:
            print(f"DEBUG: Key tables already exist. Skipping creation.")
        
        await conn.commit()
    print("DEBUG: init_models() completed.")


# FastAPI dependency to get an AsyncSession
async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

