import asyncpg, redis.asyncio as redis, os
from fastapi import APIRouter
import os
import asyncpg

router = APIRouter()

REDIS_URL = "redis://redis:6379/0"
PG_DSN     = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@postgres:5432/{os.getenv('POSTGRES_DB')}"

@router.get("/healthz", summary="Redis + Postgres check")
async def healthz():
    r = redis.from_url(REDIS_URL)
    pg = await asyncpg.connect(PG_DSN)

    await r.ping()
    await pg.fetchval("SELECT 1")

    await pg.close()
    await r.close()
    return {"ok": True}
