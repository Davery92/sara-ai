# services/dialogue_worker/main.py
"""
NATS listener that forwards chat requests to llm_proxy (/v1/stream)
and streams the chunks back to NATS.
"""
import asyncio, json, logging, os, time
from nats.aio.client import Client as NATS
import aiohttp
from prometheus_client import Counter, Histogram, start_http_server

# ── Config ────────────────────────────────────────────────────────────────
NATS_URL    = os.getenv("NATS_URL", "nats://nats:4222")
LLM_WS_URL  = os.getenv("LLM_WS_URL", "ws://llm_proxy:8000/v1/stream")
METRICS_PORT = int(os.getenv("METRICS_PORT", 8000))

TOKEN_COUNT = Counter("dw_chunk_out_total", "Chunks relayed", ["model"])

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dialogue_worker")
ACK_TIMEOUT = 3           
ACK_EVERY   = 10
TOKENS_SENT = Counter("dw_chunk_out_total", "Chunks relayed", ["model"])
CANCELLED   = Counter("dw_stream_cancel_total", "Streams cancelled – no client")
WS_LATENCY  = Histogram("dw_ws_send_seconds", "Latency NATS→LLM", buckets=(.001,.005,.01,.05,.1,.5,1,2))


# ── Helper: open a streaming request to llm_proxy ─────────────────────────
async def forward_to_llm_proxy(payload: dict, reply_subject: str, ack_subject: str, nc: NATS):
    """Stream LLM output to NATS; cancel if ACKs stop."""
    last_ack = time.monotonic()

    async def _ack_listener(msg):
        nonlocal last_ack
        last_ack = time.monotonic()

    # subscribe to the Ack subject before we start sending
    ack_sid = await nc.subscribe(ack_subject, cb=_ack_listener)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect("ws://llm_proxy:8000/v1/stream") as ws:
                await ws.send_json(payload)

                counter = 0
                async for msg in ws:
                    start = time.perf_counter()
                    await nc.publish(reply_subject, msg.data if isinstance(msg.data, bytes) else msg.data.encode())
                    WS_LATENCY.observe(time.perf_counter() - start)

                    counter += 1
                    if counter % ACK_EVERY == 0:
                        await nc.publish(ack_subject, b"+ACK")

                    # ⏱️  check for client heartbeat
                    if time.monotonic() - last_ack > ACK_TIMEOUT:
                        CANCELLED.inc()
                        logging.warning("no ACK for %ss – cancelling stream", ACK_TIMEOUT)
                        break
    finally:
        await nc.unsubscribe(ack_sid)

# ── NATS subscription callback ────────────────────────────────────────────
async def on_request(msg):
    payload       = json.loads(msg.data)
    reply_subject = msg.reply
    ack_subject   = msg.headers.get("Ack", "").decode() if msg.headers else None

    if not ack_subject:
        logging.error("missing Ack header – refusing request")
        return

    await forward_to_llm_proxy(payload, reply_subject, ack_subject, msg._client)


# ── Main event-loop ───────────────────────────────────────────────────────
async def main():
    # expose /metrics BEFORE we connect so Prom doesn’t scrape an empty target
    start_http_server(METRICS_PORT)
    log.info("Prometheus metrics on :%s/metrics", METRICS_PORT)

    nc = NATS()
    await nc.connect(servers=[NATS_URL])
    await nc.subscribe("chat.request.*", cb=on_request)
    log.info("Dialogue Worker listening on chat.request.*")
    await asyncio.Future()   # run forever


if __name__ == "__main__":
    asyncio.run(main())
