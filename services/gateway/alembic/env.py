import os
import sys
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from dotenv import load_dotenv

# ─── adjust Python path so 'app' is importable ─────────────────────────────────
# Alembic cwd is services/gateway/, so add its parent (project root) to sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, project_root)
# ─── load .env from project root ────────────────────────────────────────────────
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")))

# Build the DB URL from your .env vars
pg_user = os.environ["POSTGRES_USER"]
pg_pass = os.environ["POSTGRES_PASSWORD"]
pg_host = os.environ["POSTGRES_HOST"]
pg_port = os.environ["POSTGRES_PORT"]
pg_db   = os.environ["POSTGRES_DB"]
database_url = (
   f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"
)

# Alembic Config object
config = context.config
config.set_main_option("sqlalchemy.url", database_url)

# Logging configuration
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import your models’ metadata for autogenerate
# Ensure all your models are imported here so Base knows about them.
try:
    from services.gateway.app.database import Base  # Correct path to Base
    # Import all modules that contain your models
    from services.gateway.app.models import artifacts  # Imports your new artifact models
    # If you have other model files, import them here as well, e.g.:
    # from services.gateway.app.models import users
    # from services.gateway.app.models import other_entities
    
    target_metadata = Base.metadata
except ImportError as e:
    print(f"Error importing models for Alembic: {e}")
    print(f"Current sys.path: {sys.path}")
    target_metadata = None

def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
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
