import os, jwt, asyncio, logging
from nats.aio.client import Client as NATS
from nats.js.api import ConsumerConfig, StreamConfig
from prometheus_client import Counter

ALG   = os.getenv("JWT_ALG", "HS256")
KEY   = os.getenv("JWT_SECRET", "dev-secret-change-me")
NATS_URL = os.getenv("NATS_URL", "nats://nats:4222")
AUTH_FAILS = Counter("dw_auth_fail_total", "JWT verification failures")

def verify(tok: str):    # raises on bad sig / expiry
    try:
        return jwt.decode(tok, KEY, algorithms=[ALG])
    except jwt.PyJWTError:
        AUTH_FAILS.inc()
        raise

async def consume(loop_cb):
    nc = NATS()
    await nc.connect(servers=[NATS_URL])
    js = nc.jetstream()

    # idempotently create the CHAT stream if it’s missing
    try:
        await js.stream_info("CHAT")
    except:
        await js.add_stream(StreamConfig(name="CHAT",
                                         subjects=["chat.request.*"],
                                         storage="file",
                                         max_age=72*60*60))

    # durable pull consumer
    try:
        await js.consumer_info("CHAT", "dw")
    except:
        await js.add_consumer("CHAT",
                              ConsumerConfig(durable_name="dw",
                                             ack_policy="explicit"))

    sub = await js.pull_subscribe("chat.request.*", "dw")

    while True:
        for m in await sub.fetch(10, timeout=1):
            try:
                verify(m.header.get("Auth", ""))
                await loop_cb(m, nc)   # your existing forward-to-LLM
                await m.ack()
            except Exception as e:
                logging.warning("rejecting msg: %s", e)
                await m.term()         # dead-letter (or .nak() to retry)
        await asyncio.sleep(0.1)
