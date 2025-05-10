import asyncio
import json
import logging
import os
import time
import traceback

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
async def get_memories(user_msg: str, room_id: str, auth_token: str = None) -> list[str]:
    """Query relevant memories for the given message and room."""
    try:
        headers = {}
        if auth_token:
            headers["Authorization"] = auth_token
            log.info("🔑 Using auth token for memory retrieval")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{GATEWAY_URL}/v1/memory/query",
                json={"query": user_msg, "room_id": room_id, "top_n": MEMORY_TOP_N},
                timeout=5.0,
                headers=headers
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
async def get_persona_config(user_id: str = None, auth_token: str = None) -> str:
    """Fetch the persona configuration for the given user."""
    try:
        params = {}
        headers = {}
        
        if user_id:
            params["user_id"] = user_id
            log.info(f"🔍 Fetching persona for specific user: {user_id}")
        else:
            log.info("🔍 Fetching default persona (no user_id provided)")
        
        if auth_token:
            headers["Authorization"] = auth_token
            log.info("🔑 Using auth token for persona retrieval")
            
        async with aiohttp.ClientSession() as session:
            url = f"{GATEWAY_URL}/v1/persona/config"
            log.info(f"🔍 Making request to: {url} with params: {params}")
            
            async with session.get(
                url,
                params=params,
                timeout=5.0,
                headers=headers
            ) as resp:
                if resp.status != 200:
                    log.warning(f"❌ Persona API returned status {resp.status}")
                    response_text = await resp.text()
                    log.warning(f"❌ Response body: {response_text[:200]}...")
                    PERSONA_FAILURE.inc()
                    log.warning(f"⚠️ Using fallback system prompt: {SYS_CORE}")
                    return SYS_CORE
                
                persona_data = await resp.json()
                persona_name = persona_data.get("name", "unknown")
                log.info(f"✅ Successfully retrieved persona: {persona_name}")
                PERSONA_SUCCESS.inc()
                
                content = persona_data.get("content", SYS_CORE)
                content_preview = content.split('\n')[0] if content else "Empty content"
                log.info(f"📝 Persona content starts with: {content_preview}")
                
                return content
    except Exception as e:
        log.warning(f"❌ Failed to retrieve persona: {e}")
        traceback.print_exc()
        PERSONA_FAILURE.inc()
        log.warning(f"⚠️ Using fallback system prompt: {SYS_CORE}")
        return SYS_CORE


# ── Helper: build enhanced prompt with memories and persona ───────────────
async def enhance_prompt(payload: dict, auth_token: str = None) -> dict:
    """Add relevant memories and persona configuration to the prompt."""
    # Extract user message, room_id, and user_id
    user_msg = payload.get("msg", "")
    room_id = payload.get("room_id", "")
    user_id = payload.get("user_id", "")
    
    log.info(f"🎭 Enhancing prompt for user_id: '{user_id}', room_id: '{room_id}'")
    
    # Get persona for this user
    persona_content = await get_persona_config(user_id, auth_token)
    
    # Log first few lines of persona content for debugging
    persona_preview = '\n'.join(persona_content.split('\n')[:3]) + '...'
    log.info(f"🎭 Using persona for user '{user_id}': {persona_preview}")
    
    # Query relevant memories if we have a room and message
    memories = []
    if user_msg and room_id:
        log.info(f"📚 Retrieving memories for room '{room_id}' with query: {user_msg[:50]}...")
        memories = await get_memories(user_msg, room_id, auth_token)
    
    # Build the enhanced system prompt
    system_prompt = persona_content
    
    # Add memories if available
    if memories:
        memory_text = "\n\n".join([f"- {memory}" for memory in memories])
        system_prompt = f"{system_prompt}\n\n{MEMORY_TEMPLATE.format(memories=memory_text)}"
        log.info(f"📚 Added {len(memories)} memories to prompt")
    
    # Add prompt version metadata
    prompt_version = {
        "version": "1.0",
        "persona": user_id and "user_specific" or DEFAULT_PERSONA,
        "has_memories": bool(memories),
    }
    
    # Check if there's a messages or system_prompt field to enhance
    if "messages" in payload:
        # Find the system message if it exists
        system_msg_idx = None
        for i, msg in enumerate(payload["messages"]):
            if msg.get("role") == "system":
                system_msg_idx = i
                break
                
        if system_msg_idx is not None:
            # Replace with our enhanced system prompt
            log.info(f"🎭 Replacing existing system message with enhanced prompt at index {system_msg_idx}")
            payload["messages"][system_msg_idx]["content"] = system_prompt
        else:
            # No system message found, prepend one
            log.info(f"🎭 No system message found, adding new system message with persona")
            payload["messages"].insert(0, {
                "role": "system", 
                "content": system_prompt
            })
        
        # Log the first few messages for debugging
        for i, msg in enumerate(payload["messages"][:3]):
            role = msg.get("role", "unknown")
            content_preview = msg.get("content", "")[:50] + "..."
            log.info(f"📝 Message {i}: role={role}, content={content_preview}")
        
        # Add metadata to the payload
        payload["prompt_metadata"] = prompt_version
    else:
        # Default behavior - add system prompt
        log.info("🎭 Using default behavior - setting system_prompt directly")
        payload["system_prompt"] = system_prompt
        payload["prompt_metadata"] = prompt_version
    
    log.info(f"✅ Enhanced prompt with persona for user {user_id or 'default'}")
    if memories:
        log.info(f"✅ Enhanced prompt with {len(memories)} memories for room {room_id}")
    
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

    # Log the full payload for debugging
    log.info("🔄 Final transformed payload being sent to LLM:")
    if "messages" in payload:
        for i, msg in enumerate(payload["messages"]):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "system":
                log.info(f"📝 System message: {content}")
            elif role == "user":
                log.info(f"📝 User message: {content[:100]}...")
            else:
                log.info(f"📝 {role} message: {content[:100]}...")

    try:
        delay = 1
        max_delay = 30
        attempt = 1
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    log.info(f"Attempt {attempt}: Connecting to LLM proxy at {LLM_WS_URL}")

                    # --- Ensure required fields for LLM proxy ---
                    model_name = os.getenv("LLM_MODEL_NAME", "qwen3:32b")
                    persona_content = payload.get("system_prompt") or payload.get("persona") or ""
                    user_message = payload.get("msg") or payload.get("user_message") or ""
                    payload["model"] = model_name
                    payload["messages"] = [
                        {"role": "system", "content": persona_content},
                        {"role": "user", "content": user_message}
                    ]
                    if "prompt" in payload:
                        del payload["prompt"]
                    log.info(f"Payload to LLM proxy: {json.dumps({k: v for k, v in payload.items() if k != 'messages'}, indent=2)}\nMessages preview: {payload['messages']}")
                    # --- End ensure required fields ---

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
                        break  # Exit retry loop if successful
            except (ConnectionRefusedError, OSError) as e:
                log.warning(f"❌ LLM proxy not ready ({e}) - retrying in {delay}s (attempt {attempt})")
            except Exception as e:
                log.error(f"❌ Unexpected LLM proxy connection error: {str(e)} - retrying in {delay}s (attempt {attempt})")
                log.error(f"Error type: {type(e)}")
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
            attempt += 1
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
    enhanced_payload = await enhance_prompt(payload, auth_token)

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