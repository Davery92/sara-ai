import asyncio
import json
import logging
import os
import time

import aiohttp
from nats.aio.client import Client as NATS   # only for type-hint / publish
from prometheus_client import Counter, Histogram, start_http_server

from jetstream import consume                # durable pull-consumer helper


# ── Config ────────────────────────────────────────────────────────────────
NATS_URL     = os.getenv("NATS_URL", "nats://nats:4222")
LLM_WS_URL   = os.getenv("LLM_WS_URL", "ws://llm_proxy:8000/v1/stream")
METRICS_PORT = int(os.getenv("METRICS_PORT", 8000))

ACK_TIMEOUT  = 3           # seconds without +ACK before cancelling the stream
ACK_EVERY    = 10          # send an ACK to the client after this many chunks


# ── Prometheus metrics ────────────────────────────────────────────────────
CHUNKS_RELAYED = Counter(
    "dw_chunk_out_total",
    "Chunks relayed to NATS",
    ["model"],
)
CANCELLED = Counter(
    "dw_stream_cancel_total",
    "Streams cancelled due to missing client ACK",
)
WS_LATENCY = Histogram(
    "dw_ws_send_seconds",
    "Latency for each chunk NATS → LLM proxy",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 2),
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dialogue_worker")


# ── Helper: open a streaming request to llm_proxy ─────────────────────────
async def forward_to_llm_proxy(
    payload: dict,
    reply_subject: str,
    ack_subject: str,
    nc: NATS,
):
    """Stream LLM output to NATS; cancel if ACKs stop."""
    last_ack = time.monotonic()

    async def _ack_listener(msg):
        nonlocal last_ack
        last_ack = time.monotonic()

    # Subscribe to the ACK subject before we start sending
    ack_sid = await nc.subscribe(ack_subject, cb=_ack_listener)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(LLM_WS_URL) as ws:
                await ws.send_json(payload)

                counter = 0
                async for msg in ws:
                    start = time.perf_counter()
                    await nc.publish(
                        reply_subject,
                        msg.data if isinstance(msg.data, bytes) else msg.data.encode(),
                    )
                    WS_LATENCY.observe(time.perf_counter() - start)

                    # Metric bump
                    model = payload.get("model", "unknown")
                    CHUNKS_RELAYED.labels(model=model).inc()

                    counter += 1
                    if counter % ACK_EVERY == 0:
                        await nc.publish(ack_subject, b"+ACK")

                    # ⏱️  Check for client heartbeat
                    if time.monotonic() - last_ack > ACK_TIMEOUT:
                        CANCELLED.inc()
                        log.warning("no ACK for %ss – cancelling stream", ACK_TIMEOUT)
                        break
    finally:
        await nc.unsubscribe(ack_sid)


# ── NATS subscription callback ────────────────────────────────────────────
async def on_request(msg, nc):
    payload       = json.loads(msg.data)
    reply_subject = msg.reply
    ack_subject   = msg.headers.get("Ack", "")

    if not ack_subject:
        log.error("missing Ack header – refusing request")
        return

    await forward_to_llm_proxy(payload, reply_subject, ack_subject, nc)


# ── Main event-loop ───────────────────────────────────────────────────────
async def main():
    # Expose /metrics before connecting so Prom doesn’t scrape an empty target
    start_http_server(METRICS_PORT)
    log.info("Prometheus metrics on :%s/metrics", METRICS_PORT)

    # JetStream pull-loop → on_request (runs forever)
    await consume(on_request)


if __name__ == "__main__":
    asyncio.run(main())