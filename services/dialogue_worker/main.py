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
GATEWAY_URL  = os.getenv("GATEWAY_URL", "http://gateway:8000")
METRICS_PORT = int(os.getenv("METRICS_PORT", 8000))
MEMORY_TOP_N = int(os.getenv("MEMORY_TOP_N", 3))  # Number of memories to include in prompt
DEFAULT_PERSONA = os.getenv("DEFAULT_PERSONA", "sara_default")

# System prompt templates
SYS_CORE = os.getenv("SYSTEM_PROMPT", "You are a helpful AI assistant.")
MEMORY_TEMPLATE = os.getenv("MEMORY_TEMPLATE", "Previous conversation summaries:\n{memories}")

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
MEMORY_SUCCESS = Counter(
    "dw_memory_success_total",
    "Successful memory retrievals",
)
MEMORY_FAILURE = Counter(
    "dw_memory_failure_total",
    "Failed memory retrievals",
)
PERSONA_SUCCESS = Counter(
    "dw_persona_success_total",
    "Successful persona retrievals",
)
PERSONA_FAILURE = Counter(
    "dw_persona_failure_total",
    "Failed persona retrievals",
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dialogue_worker")


# ── Helper: query memories from gateway ───────────────────────────────────
async def get_memories(user_msg: str, room_id: str) -> list[str]:
    """Query relevant memories for the given message and room."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GATEWAY_URL}/v1/memory/query",
                json={"query": user_msg, "room_id": room_id, "top_n": MEMORY_TOP_N},
                timeout=5.0,
            ) as resp:
                if resp.status != 200:
                    log.warning(f"Memory API returned status {resp.status}")
                    MEMORY_FAILURE.inc()
                    return []
                
                memories = await resp.json()
                MEMORY_SUCCESS.inc()
                return [memory["text"] for memory in memories]
    except Exception as e:
        log.warning(f"Failed to retrieve memories: {e}")
        MEMORY_FAILURE.inc()
        return []


# ── Helper: fetch persona from gateway ──────────────────────────────────
async def get_persona_config(user_id: str = None) -> str:
    """Fetch the persona configuration for the given user."""
    try:
        params = {}
        if user_id:
            params["user_id"] = user_id
            
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{GATEWAY_URL}/v1/persona/config",
                params=params,
                timeout=5.0,
            ) as resp:
                if resp.status != 200:
                    log.warning(f"Persona API returned status {resp.status}")
                    PERSONA_FAILURE.inc()
                    return SYS_CORE
                
                persona_data = await resp.json()
                PERSONA_SUCCESS.inc()
                return persona_data.get("content", SYS_CORE)
    except Exception as e:
        log.warning(f"Failed to retrieve persona: {e}")
        PERSONA_FAILURE.inc()
        return SYS_CORE


# ── Helper: build enhanced prompt with memories and persona ───────────────
async def enhance_prompt(payload: dict) -> dict:
    """Add relevant memories and persona configuration to the prompt."""
    # Extract user message, room_id, and user_id
    user_msg = payload.get("msg", "")
    room_id = payload.get("room_id", "")
    user_id = payload.get("user_id", "")
    
    # Get persona for this user
    persona_content = await get_persona_config(user_id)
    
    # Query relevant memories if we have a room and message
    memories = []
    if user_msg and room_id:
        memories = await get_memories(user_msg, room_id)
    
    # Build the enhanced system prompt
    system_prompt = persona_content
    
    # Add memories if available
    if memories:
        memory_text = "\n\n".join([f"- {memory}" for memory in memories])
        system_prompt = f"{system_prompt}\n\n{MEMORY_TEMPLATE.format(memories=memory_text)}"
    
    # Add prompt version metadata
    prompt_version = {
        "version": "1.0",
        "persona": user_id and "user_specific" or DEFAULT_PERSONA,
        "has_memories": bool(memories),
    }
    
    # Check if there's a messages or system_prompt field to enhance
    if "messages" in payload:
        # Find the system message if it exists
        for i, msg in enumerate(payload["messages"]):
            if msg.get("role") == "system":
                # Replace with our enhanced system prompt
                payload["messages"][i]["content"] = system_prompt
                break
        else:
            # No system message found, prepend one
            payload["messages"].insert(0, {
                "role": "system", 
                "content": system_prompt
            })
        
        # Add metadata to the payload
        payload["prompt_metadata"] = prompt_version
    else:
        # Default behavior - add system prompt
        payload["system_prompt"] = system_prompt
        payload["prompt_metadata"] = prompt_version
    
    log.info(f"Enhanced prompt with persona for user {user_id or 'default'}")
    if memories:
        log.info(f"Enhanced prompt with {len(memories)} memories for room {room_id}")
    
    return payload


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

    # NEW: guard against missing Auth
    auth_token = (msg.headers or {}).get("Auth", "")
    if not auth_token:
        log.warning("rejecting msg: missing Auth header")
        return

    # Enhance the prompt with persona and memories
    enhanced_payload = await enhance_prompt(payload)

    await forward_to_llm_proxy(enhanced_payload, reply_subject, ack_subject, nc)



# ── Main event-loop ───────────────────────────────────────────────────────
async def main():
    # Expose /metrics before connecting so Prom doesn't scrape an empty target
    start_http_server(METRICS_PORT)
    log.info("Prometheus metrics on :%s/metrics", METRICS_PORT)

    # JetStream pull-loop → on_request (runs forever)
    await consume(on_request)


if __name__ == "__main__":
    asyncio.run(main())