# services/dialogue_worker/main.py
"""
NATS listener that forwards chat requests to llm_proxy (/v1/stream)
and streams the chunks back to NATS.
"""
import asyncio, json, logging, os
from nats.aio.client import Client as NATS
import aiohttp

# ── Config ────────────────────────────────────────────────────────────────
NATS_URL   = os.getenv("NATS_URL",   "nats://nats:4222")
LLM_PROXY  = os.getenv("LLM_PROXY",  "http://llm_proxy:8000")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dialogue_worker")


# ── Helper: open a single streaming request to llm_proxy ──────────────────
async def forward_to_llm_proxy(payload: dict, reply_subject: str, nc: NATS):
    """
    1. WebSocket-connect to llm_proxy:/v1/stream
    2. Send the JSON payload
    3. For every token chunk that comes back, publish it to NATS `reply_subject`
    """
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(f"{LLM_PROXY}/v1/stream") as ws:
            # Send the initial JSON body *once*.
            await ws.send_json(payload)

            # Relay every token chunk back to NATS.
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    await nc.publish(reply_subject, msg.data)
                elif msg.type == aiohttp.WSMsgType.TEXT:
                    await nc.publish(reply_subject, msg.data.encode())
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    raise ws.exception()


# ── NATS subscription callback ────────────────────────────────────────────
async def on_request(msg):
    """
    Triggered for every message on subjects that match 'chat.request.*'
    """
    try:
        payload       = json.loads(msg.data)
        reply_subject = msg.reply             # already set by Gateway
        await forward_to_llm_proxy(payload, reply_subject, msg._client)
    except Exception as e:
        log.exception("worker failed: %s", e)
        
        if msg.reply:
            # Only try to reply if reply_subject actually exists
            await msg._client.publish(
                msg.reply,
                json.dumps({"error": str(e)}).encode()
            )
        else:
            log.error("Cannot reply to sender: missing reply subject.")



# ── Main event-loop ───────────────────────────────────────────────────────
async def main():
    nc = NATS()
    await nc.connect(servers=[NATS_URL])
    # Wild-card so a *single* worker can handle every session ID.
    await nc.subscribe("chat.request.*", cb=on_request)
    log.info("Dialogue Worker listening on chat.request.*")
    await asyncio.Future()   # run forever


if __name__ == "__main__":
    asyncio.run(main())
