import os, sys, time, redis, psycopg2, nats
from nats.aio.client import Client as NATS
import asyncio

def ok(label): print(f"✅ {label}")

# Redis
r = redis.Redis(host="redis", port=6379, decode_responses=True)
r.set("ping", "pong")
assert r.get("ping") == "pong"
ok("Redis")

# Postgres
pg = psycopg2.connect(
    host="postgres",
    user=os.getenv("POSTGRES_USER", "sara"),
    password=os.getenv("POSTGRES_PASSWORD", "sara_pw"),
    dbname=os.getenv("POSTGRES_DB", "sara"),
)
cur = pg.cursor()
cur.execute("SELECT 1;")
assert cur.fetchone()[0] == 1
ok("Postgres")

# NATS
async def nats_roundtrip():
    nc = NATS()
    await nc.connect("nats://nats:4222")
    subj, data = "health.ping", b"ok"
    fut = asyncio.create_task(nc.next_msg(subj, timeout=1))
    await nc.publish(subj, data)
    await nc.flush()
    msg = await fut
    assert msg.data == data
    await nc.close()
asyncio.run(nats_roundtrip())
ok("NATS")

print("🎉 ALL GREEN")

