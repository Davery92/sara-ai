# services/gateway/app/settings.py
import os

# In prod you’ll export PG_DSN; during unit-tests we fall
# back to a dummy value so asyncpg never even dials.
PG_DSN: str = os.getenv(
    "PG_DSN",
    "postgresql://postgres:postgres@localhost:5432/postgres",
)
