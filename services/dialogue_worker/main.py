import asyncio
import json
import logging
import os
import time
import traceback
import aiohttp

from nats.aio.client import Client as NATS
from prometheus_client import Counter, Histogram, start_http_server
from jetstream import verify, consume
from jwt.exceptions import InvalidTokenError
import websockets

# ── Config ───────────────────────────────────────────────────────────────
NATS_URL      = os.getenv("NATS_URL",  "nats://nats:4222")
LLM_WS_URL    = os.getenv("LLM_WS_URL","ws://llm_proxy:8000/v1/stream")
GATEWAY_URL   = os.getenv("GATEWAY_URL","http://gateway:8000")
LLM_MODEL     = os.getenv("LLM_MODEL", "qwen3:32b")
METRICS_PORT  = int(os.getenv("METRICS_PORT", 8000))
MEMORY_TOP_N  = int(os.getenv("MEMORY_TOP_N", 3))
DEFAULT_PERSONA = os.getenv("DEFAULT_PERSONA", "sara_default")

SYS_CORE        = os.getenv("SYSTEM_PROMPT","You are a helpful AI assistant.")
MEMORY_TEMPLATE = os.getenv("MEMORY_TEMPLATE","Previous conversation summaries:\n{memories}")

ACK_TIMEOUT = 15
ACK_EVERY   = 10

# ── Prometheus metrics ───────────────────────────────────────────────────
CHUNKS_RELAYED = Counter("dw_chunk_out_total", "Chunks relayed to NATS", ["model"])
CANCELLED      = Counter("dw_stream_cancel_total","Streams cancelled — idle")
WS_LATENCY     = Histogram("dw_ws_send_seconds","Latency per chunk", buckets=(0.001,0.005,0.01,0.05,0.1,0.5,1,2))
MEMORY_SUCCESS = Counter("dw_memory_success_total","Successful memory retrievals")
MEMORY_FAILURE = Counter("dw_memory_failure_total","Failed memory retrievals")
PERSONA_SUCCESS= Counter("dw_persona_success_total","Successful persona retrievals")
PERSONA_FAILURE= Counter("dw_persona_failure_total","Failed persona retrievals")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dialogue_worker")

def build_llm_payload(user_payload: dict) -> dict:
    return {
        "model": user_payload.get("model") or LLM_MODEL,
        "messages": user_payload.get("messages", [{"role": "user", "content": user_payload.get("msg", "")}]),
        "stream": True,
    }

async def get_memories(user_msg: str, room_id: str, auth_token: str = None) -> list[str]:
    try:
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GATEWAY_URL}/v1/memory/query",
                json={"query": user_msg, "room_id": room_id, "top_n": MEMORY_TOP_N},
                timeout=5.0,
                headers=headers
            ) as resp:
                if resp.status != 200:
                    MEMORY_FAILURE.inc()
                    return []
                memories = await resp.json()
                MEMORY_SUCCESS.inc()
                return [memory["text"] for memory in memories]
    except Exception:
        MEMORY_FAILURE.inc()
        return []

async def get_persona_config(user_id: str = None, auth_token: str = None) -> str:
    try:
        headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}
        params = {"user_id": user_id} if user_id else {}
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{GATEWAY_URL}/v1/persona/config", params=params, timeout=5.0, headers=headers) as resp:
                if resp.status != 200:
                    PERSONA_FAILURE.inc()
                    return SYS_CORE
                data = await resp.json()
                PERSONA_SUCCESS.inc()
                return data.get("content", SYS_CORE)
    except Exception:
        PERSONA_FAILURE.inc()
        return SYS_CORE

async def enhance_prompt(payload: dict, auth_token: str = None) -> dict:
    user_msg = payload.get("msg", "")
    room_id = payload.get("room_id", "")
    user_id = payload.get("user_id", "")

    persona_content = await get_persona_config(user_id, auth_token)
    memories = await get_memories(user_msg, room_id, auth_token) if user_msg and room_id else []

    system_prompt = persona_content
    if memories:
        memory_text = "\n\n".join([f"- {m}" for m in memories])
        system_prompt += f"\n\n{MEMORY_TEMPLATE.format(memories=memory_text)}"

    if "messages" in payload:
        for msg in payload["messages"]:
            if msg.get("role") == "system":
                msg["content"] = system_prompt
                break
        else:
            payload["messages"].insert(0, {"role": "system", "content": system_prompt})
    else:
        payload["system_prompt"] = system_prompt

    return payload

async def forward_to_llm_proxy(payload: dict, reply_subject: str, ack_subject: str, nc: NATS):
    last_ack   = time.monotonic()
    INIT_ACK   = b"+INIT_ACK"
    CHUNK_ACK  = b"+ACK"

    async def _ack_listener(_msg):
        nonlocal last_ack
        last_ack = time.monotonic()

    ack_sid = await nc.subscribe(ack_subject, cb=_ack_listener)
    llm_payload = build_llm_payload(payload)
    model_name  = llm_payload["model"]

    try:
        # Increased connection timeout for better reliability
        async with websockets.connect(LLM_WS_URL, close_timeout=5.0) as ws:
            log.info("✅ Connected to llm_proxy (%s) – sending prompt", model_name)
            await ws.send(json.dumps(llm_payload))
            await nc.publish(ack_subject, INIT_ACK)

            chunk_no = 0
            try:
                async for message in ws:
                    # Check for error response from LLM proxy
                    try:
                        parsed = json.loads(message)
                        if "error" in parsed:
                            error_msg = parsed["error"]
                            log.error(f"LLM proxy returned error: {error_msg}")
                            await nc.publish(reply_subject, json.dumps({"error": f"LLM service error: {error_msg}"}).encode())
                            return
                    except json.JSONDecodeError:
                        pass  # Not JSON, continue normal processing

                    data = message.encode()
                    await nc.publish(reply_subject, data)
                    CHUNKS_RELAYED.labels(model=model_name).inc()

                    chunk_no += 1
                    if chunk_no % ACK_EVERY == 0:
                        await nc.publish(ack_subject, CHUNK_ACK)

                    if time.monotonic() - last_ack > ACK_TIMEOUT:
                        CANCELLED.inc()
                        log.warning("⚠️  client idle >%s s – cancelling", ACK_TIMEOUT)
                        await ws.close()
                        break
            finally:
                await nc.publish(reply_subject, b"[DONE]")
                await ack_sid.unsubscribe()
    except websockets.exceptions.WebSocketException as e:
        log.error(f"WebSocket error: {e}")
        await nc.publish(reply_subject, json.dumps({"error": f"Failed to connect to LLM service: {str(e)}"}).encode())
    except Exception as e:
        log.exception(f"Error in LLM proxy communication: {e}")
        await nc.publish(reply_subject, json.dumps({"error": f"Internal error: {str(e)}"}).encode())


async def on_request(msg, nc):
    hdrs = msg.headers or {}
    reply_subject = hdrs.get("Reply")
    ack_subject   = hdrs.get("Ack")
    auth_token    = hdrs.get("Auth")

    if not (reply_subject and ack_subject and auth_token):
        log.error("Missing required headers – dropping message")
        # Send error message to client if reply subject is available
        if reply_subject:
            await nc.publish(reply_subject, json.dumps({
                "error": "Missing required headers"
            }).encode())
        await msg.term()
        return

    for field in ("Reply", "Ack", "Auth"):
        if isinstance(hdrs.get(field), bytes):
            hdrs[field] = hdrs[field].decode()

    try:
        verify(auth_token)
    except InvalidTokenError:
        log.warning("JWT verify failed")
        # Notify client of auth failure
        if reply_subject:
            await nc.publish(reply_subject, json.dumps({
                "error": "Authentication failed"
            }).encode())
        await msg.term()
        return

    try:
        payload = json.loads(msg.data)
    except Exception as e:
        log.warning(f"Bad JSON payload: {e}")
        if reply_subject:
            await nc.publish(reply_subject, json.dumps({
                "error": f"Invalid request format: {str(e)}"
            }).encode())
        await msg.term()
        return

    try:
        enhanced = await enhance_prompt(payload, auth_token)
        await forward_to_llm_proxy(enhanced, reply_subject=reply_subject, ack_subject=ack_subject, nc=nc)
        await msg.ack()
    except Exception as e:
        log.exception(f"Processing failed: {e}")
        if reply_subject:
            await nc.publish(reply_subject, json.dumps({
                "error": f"Request processing failed: {str(e)}"
            }).encode())
        await msg.term()

async def main():
    start_http_server(METRICS_PORT)
    log.info("Prometheus metrics on :%s/metrics", METRICS_PORT)
    await consume(on_request)

if __name__ == "__main__":
    asyncio.run(main())
