import os, jwt, asyncio, logging
from nats.aio.client import Client as NATS
from nats.js.api import ConsumerConfig
from prometheus_client import Counter

ALG   = os.getenv("JWT_ALG",  "HS256")
KEY   = os.getenv("JWT_KEY",  os.getenv("JWT_SECRET", "dev-secret-change-me"))
NATS_URL = os.getenv("NATS_URL", "nats://nats:4222")

AUTH_FAILS = Counter("dw_auth_fail_total", "JWT verification failures")

def verify(token: str):
    try:
        return jwt.decode(token, KEY, algorithms=[ALG])
    except jwt.PyJWTError:
        AUTH_FAILS.inc()
        raise

async def consume(loop_cb):
    nc = NATS()
    await nc.connect(servers=[NATS_URL])
    js = nc.jetstream()

    # Create a durable pull consumer if it doesn’t exist
    try:
        await js.stream_info("CHAT")            # already there?
    except Exception:
        cfg = StreamConfig(
            name="CHAT",
            subjects=["chat.request.*"],
            storage="file",
            retention="limits",
            max_age=72*60*60)                   # secs
        await js.add_stream(cfg)

    sub = await js.pull_subscribe("chat.request.*", "dw")

    while True:
        for msg in await sub.fetch(10, timeout=1):
            try:
                jwt_raw = msg.header.get("Auth", "")
                verify(jwt_raw)
                await loop_cb(msg, nc)        # ← your existing forward_to_llm_proxy
                await msg.ack()
            except Exception as e:
                logging.warning("rejecting msg: %s", e)
                await msg.term()              # drop (or use nak() to retry)
        await asyncio.sleep(0.1)
