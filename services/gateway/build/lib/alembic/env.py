# services/gateway/alembic/env.py
import os
import sys
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv

# --- DEBUGGING PRINTS START ---
print("DEBUG: env.py started execution.")

# ─── adjust Python path so 'app' is importable ─────────────────────────────────
# Alembic cwd is services/gateway/, so add its parent (project root) to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, project_root)
print(f"DEBUG: Current working directory: {os.getcwd()}")
print(f"DEBUG: sys.path after prepend: {sys.path}")

# ─── load .env from project root ────────────────────────────────────────────────
dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
load_dotenv(dotenv_path=dotenv_path)
print(f"DEBUG: Loaded .env from: {dotenv_path}")

# Build the DB URL from your .env vars
pg_user = os.environ.get("POSTGRES_USER")
pg_pass = os.environ.get("POSTGRES_PASSWORD")
pg_host = os.environ.get("POSTGRES_HOST")
pg_port = os.environ.get("POSTGRES_PORT")
pg_db   = os.environ.get("POSTGRES_DB")

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
    # --- IMPORTANT ---
    # Import ALL models that define tables for Base.metadata
    from services.gateway.app.db.models import Base, User, Memory, Chat, ChatMessage, EmbeddingMessage
    # Assuming you've created these as part of your plan
    
    print(f"DEBUG: Successfully imported all models (Base, User, Memory, Chat, ChatMessage).")
    target_metadata = Base.metadata
except ImportError as e:
    print(f"ERROR: Failed to import models for Alembic. This is critical: {e}")
    # If models can't be imported, Alembic can't compare schema. Exit.
    target_metadata = None
    sys.exit(1) # Ensure process exits on critical import error

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
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

print("DEBUG: env.py finished execution.")
# --- DEBUGGING PRINTS END ---