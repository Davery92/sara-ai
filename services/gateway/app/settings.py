# services/gateway/app/settings.py
import os
import logging

# add logging to help debug
logger = logging.getLogger(__name__)

POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

class Settings:
    pg_dsn = os.getenv(
        "PG_DSN",
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    # Debug logging
    logger.info(f"Connecting to database: postgresql://{POSTGRES_USER}:****@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")
    
    nats_url = os.getenv("NATS_URL", "nats://nats:4222")
    llm_proxy_url = os.getenv("LLM_PROXY_URL", "http://llm_proxy:8000")
    jwt_secret = os.getenv("JWT_SECRET", "dev-secret-change-me")

settings = Settings()