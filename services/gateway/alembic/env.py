# services/gateway/alembic/env.py
import os
import sys
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv

# --- DEBUGGING PRINTS START ---
print("DEBUG: env.py started execution.")

# ─── Adjust Python path and load .env ──────────────────────────────────────────
# Get the absolute path of the current directory (services/gateway/alembic)
current_dir = os.path.abspath(os.path.dirname(__file__))

# Project root is three levels up from current_dir: services/gateway/alembic -> services/gateway -> services -> sara-ai
project_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))

# Add the project root to sys.path FIRST to ensure top-level imports work
if project_root not in sys.path:
    sys.path.insert(0, project_root)

print(f"DEBUG: Current working directory: {os.getcwd()}")
print(f"DEBUG: Project root added to sys.path: {project_root}")
print(f"DEBUG: sys.path after prepend: {sys.path}")

# Load .env from the project root
dotenv_path = os.path.join(project_root, ".env") # <--- CORRECTED .env path
load_dotenv(dotenv_path=dotenv_path)
print(f"DEBUG: Loaded .env from: {dotenv_path}")

# Build the DB URL from your .env vars
pg_user = os.environ.get("POSTGRES_USER")
pg_pass = os.environ.get("POSTGRES_PASSWORD")
pg_host = os.environ.get("POSTGRES_HOST")
pg_port = os.environ.get("POSTGRES_PORT")
pg_db   = os.environ.get("POSTGRES_DB")

# IMPORTANT: Print debug info for env vars to confirm they're loaded
print(f"DEBUG: POSTGRES_USER: {pg_user}")
print(f"DEBUG: POSTGRES_HOST: {pg_host}")
print(f"DEBUG: POSTGRES_PORT: {pg_port}")
print(f"DEBUG: POSTGRES_DB: {pg_db}")


# IMPORTANT: Do NOT print the full password.
database_url = (
   f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
)
print(f"DEBUG: Constructed DATABASE_URL (partial): postgresql://{pg_user}:****@{pg_host}:{pg_port}/{pg_db}")

# Alembic Config object
config = context.config
config.set_main_option("sqlalchemy.url", database_url)

# Logging configuration
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import your models’ metadata for autogenerate
# Ensure all your models are imported here so Base knows about them.
try:
    # Import ALL models that define tables for Base.metadata
    # Make sure this import is now correct given the fixed sys.path
    from services.gateway.app.db.models import Base, User, Memory, Chat, ChatMessage, EmbeddingMessage
    
    print(f"DEBUG: Successfully imported all models (Base, User, Memory, Chat, ChatMessage, EmbeddingMessage).")
    target_metadata = Base.metadata
except ImportError as e:
    print(f"ERROR: Failed to import models for Alembic. This is critical: {e}")
    target_metadata = None
    sys.exit(1)

def run_migrations_offline() -> None:
    print("DEBUG: Running migrations offline.")
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    print("DEBUG: Running migrations online.")
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
            )
            with context.begin_transaction():
                context.run_migrations()
    except Exception as e:
        print(f"ERROR: Exception during online migration execution: {e}")
        # Add more specific logging here if needed, e.g. for connection errors
        raise # Re-raise to fail the process

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

print("DEBUG: env.py finished execution.")
# --- DEBUGGING PRINTS END ---