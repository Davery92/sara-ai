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
WS_LATENCY  = Histogram("dw_ws_send_seconds", "WS chunk relay latency seconds")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dialogue_worker")


# ── Helper: open a streaming request to llm_proxy ─────────────────────────
async def forward_to_llm_proxy(payload: dict, reply_subject: str, nc: NATS):
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(LLM_WS_URL) as ws:
            await ws.send_json(payload)

            async for msg in ws:
                if msg.type not in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                    continue

                start = time.perf_counter()
                await nc.publish(reply_subject, msg.data if isinstance(msg.data, bytes) else msg.data.encode())
                WS_LATENCY.observe(time.perf_counter() - start)
                TOKEN_COUNT.labels(payload.get("model", "unknown")).inc()


# ── NATS subscription callback ────────────────────────────────────────────
async def on_request(msg):
    payload = json.loads(msg.data)
    reply_subject = msg.reply

    try:
        await forward_to_llm_proxy(payload, reply_subject, msg._client)
    except Exception as e:
        log.exception("worker failed")
        if reply_subject:
            await msg._client.publish(reply_subject, json.dumps({"error": str(e)}).encode())


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
