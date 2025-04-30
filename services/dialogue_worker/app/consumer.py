import os, jwt, asyncio, logging, json
from nats.aio.client import Client as NATS
from nats.js.api import ConsumerConfig
from prometheus_client import Counter

JWT_ALG  = os.getenv("JWT_ALG", "HS256")
JWT_KEY  = open("/run/secrets/jwt_public.pem").read() if JWT_ALG == "RS256" else os.getenv("JWT_SECRET")
AUTH_FAILS = Counter("dw_auth_fail_total", "JWT failures in Dialogue-Worker")

def verify(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_KEY, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        AUTH_FAILS.inc()
        raise

async def consume_loop():
    nc = NATS()
    await nc.connect(servers=["nats://nats:4222"])
    js = nc.jetstream()

    # durable pull consumer
    ccfg = ConsumerConfig(durable_name="dw", ack_policy="explicit")
    await js.consumer_info("CHAT", "dw").catch(lambda _: js.add_consumer("CHAT", ccfg))

    sub = await js.pull_subscribe("chat.request.*", "dw")

    while True:
        msgs = await sub.fetch(10, timeout=1)
        for m in msgs:
            try:
                hdr = m.header.get("Auth")
                claims = verify(hdr)
                # forward to LLM-Proxy here …
                await m.ack()
            except Exception as e:
                logging.warning("rejecting msg: %s", e)
                await m.term()           # drop or `nak()` for retry
        await asyncio.sleep(0.1)
