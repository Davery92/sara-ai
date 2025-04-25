import os, redis, psycopg2, asyncio
from nats.aio.client import Client as NATS

def ok(label): print(f"✅ {label}")

# Redis ------------------------------------------------------------
r = redis.Redis(host="redis", port=6379, decode_responses=True)
r.set("ping", "pong")
assert r.get("ping") == "pong"
ok("Redis")

# Postgres ---------------------------------------------------------
pg = psycopg2.connect(
    host="postgres",
    user=os.getenv("POSTGRES_USER", "sara"),
    password=os.getenv("POSTGRES_PASSWORD", "sara_pw"),
    dbname=os.getenv("POSTGRES_DB", "sara"),
)
pg.cursor().execute("SELECT 1;")
ok("Postgres")

# NATS -------------------------------------------------------------
async def nats_ping():
    nc = NATS()
    await nc.connect("nats://nats:4222", connect_timeout=1)
    await nc.flush()          # round-trip with server
    await nc.close()

asyncio.run(nats_ping())
ok("NATS")

print("🎉 ALL GREEN")

