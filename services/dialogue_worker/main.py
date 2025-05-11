import asyncio
import json
import logging
import os
import time
import traceback

import aiohttp
from nats.aio.client import Client as NATS   
from prometheus_client import Counter, Histogram, start_http_server
from jetstream import verify
from jetstream import consume                
from jwt.exceptions import InvalidTokenError


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

ACK_TIMEOUT  = 15          # seconds without +ACK before cancelling the stream (increased from 3)
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
            headers["Authorization"] = f"Bearer {auth_token}"
            log.info("🔑 Using auth token for memory retrieval")
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{GATEWAY_URL}/v1/memory/query",
                    json={"query": user_msg, "room_id": room_id, "top_n": MEMORY_TOP_N},
                    timeout=5.0,
                    headers=headers
                ) as resp:
                    if resp.status != 200:
                        log.warning(f"Memory API returned status {resp.status}")
                        # Try to get response body for better debugging
                        try:
                            error_body = await resp.text()
                            log.warning(f"Memory API error response: {error_body[:200]}...")
                        except Exception:
                            log.warning("Could not read error response body")
                        MEMORY_FAILURE.inc()
                        return []
                    
                    memories = await resp.json()
                    MEMORY_SUCCESS.inc()
                    return [memory["text"] for memory in memories]
            except aiohttp.ClientError as e:
                log.warning(f"Network error during memory retrieval: {e}")
                MEMORY_FAILURE.inc()
                return []
    except Exception as e:
        log.warning(f"Failed to retrieve memories: {e}")
        traceback.print_exc()
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
            headers["Authorization"] = f"Bearer {auth_token}"
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
    """
    Forward the request to llm_proxy, relay every chunk back to the
    browser through NATS, and honour client ACKs.
    """
    # ------------------------------------------------------------------ #
    # 1.  heartbeat bookkeeping
    # ------------------------------------------------------------------ #
    last_ack  = time.monotonic()          # updated each time we see +ACK
    CHUNK_ACK = b"+ACK"
    INIT_ACK  = b"+INIT_ACK"

    async def _ack_listener(_msg):        # ←  **the fix – async coroutine**
        nonlocal last_ack
        last_ack = time.monotonic()

    ack_sid = await nc.subscribe(ack_subject, cb=_ack_listener)

    # ------------------------------------------------------------------ #
    # 2.  open websocket to llm_proxy and start streaming
    # ------------------------------------------------------------------ #
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(LLM_WS_URL, timeout=20) as ws:
            log.info("✅ Connected to llm_proxy – sending prompt")
            await ws.send_json(payload)
            await nc.publish(ack_subject, INIT_ACK)

            chunk_no = 0
            try:
                async for ws_msg in ws:
                    if ws_msg.type not in (
                        aiohttp.WSMsgType.TEXT,
                        aiohttp.WSMsgType.BINARY,
                    ):
                        continue                                      # ignore pings

                    # relay chunk to frontend
                    data = ws_msg.data if isinstance(ws_msg.data, bytes) else ws_msg.data.encode()
                    await nc.publish(reply_subject, data)
                    CHUNKS_RELAYED.labels(model=payload.get("model", "unknown")).inc()

                    # periodic heartbeat back to client
                    chunk_no += 1
                    if chunk_no % ACK_EVERY == 0:
                        await nc.publish(ack_subject, CHUNK_ACK)

                    # cancel if the browser stops ACK-ing
                    if time.monotonic() - last_ack > ACK_TIMEOUT:
                        CANCELLED.inc()
                        log.warning("⚠️  client idle >%s s – cancelling", ACK_TIMEOUT)
                        await ws.close()
                        break
            finally:
                await nc.publish(reply_subject, b"[DONE]")
                await nc.unsubscribe(ack_sid)


# ── NATS subscription callback ────────────────────────────────────────────
# ── dialogue_worker/main.py  ─────────────────────────────────────────────
async def on_request(msg, nc):
    """
    Validate headers, enhance the prompt, forward the stream,
    and ACK or TERM the JetStream message.
    """
    hdrs = msg.headers or {}

    reply_subject = hdrs.get("Reply")
    ack_subject   = hdrs.get("Ack")
    auth_token    = hdrs.get("Auth")

    # all three headers are required
    if not (reply_subject and ack_subject and auth_token):
        log.error("Missing required headers – dropping message")
        await msg.term()
        return

    # make sure they’re str
    if isinstance(reply_subject, bytes):
        reply_subject = reply_subject.decode()
    if isinstance(ack_subject,   bytes):
        ack_subject   = ack_subject.decode()
    if isinstance(auth_token,    bytes):
        auth_token    = auth_token.decode()

    # verify JWT
    try:
        verify(auth_token)                       # raises on bad / expired
    except InvalidTokenError as e:
        log.warning("JWT verify failed: %s", e)
        await msg.term()
        return

    # decode body
    try:
        payload = json.loads(msg.data)
    except Exception as e:
        log.warning("Bad JSON payload: %s", e)
        await msg.term()
        return

    try:
        # persona + memory enrichment
        enhanced = await enhance_prompt(payload, auth_token)

        # relay to LLM proxy (handles its own heart-beats)
        await forward_to_llm_proxy(
            enhanced,
            reply_subject=reply_subject,
            ack_subject=ack_subject,
            nc=nc,
        )

        await msg.ack()                          # success 🎉
    except Exception as e:
        log.exception("Processing failed: %s", e)
        await msg.term()
                # don’t redeliver




# ── Helper: check LLM proxy status ─────────────────────────────────────────
async def check_llm_proxy_health():
    """Check if the LLM proxy is responsive."""
    http_url = LLM_WS_URL.replace('ws://', 'http://').replace('wss://', 'https://')
    base_url = http_url.split('/v1/')[0]
    
    # Try multiple possible health check endpoints
    health_endpoints = ['/healthz', '/health', '/ping', '/']
    
    for endpoint in health_endpoints:
        health_url = f"{base_url}{endpoint}"
        log.info(f"🏥 Checking LLM proxy health at {health_url}")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(health_url, timeout=5.0) as resp:
                    if resp.status < 400:  # Any 2xx or 3xx response
                        log.info(f"✅ LLM proxy is healthy - responded to {health_url}")
                        return True
                    else:
                        log.warning(f"❌ LLM proxy endpoint {health_url} returned status {resp.status}")
        except Exception as e:
            log.warning(f"❌ Failed to connect to LLM proxy health endpoint {health_url}: {e}")
    
    # If we reach this point, all health check attempts have failed
    log.error("❌ All LLM proxy health checks failed")
    return False


# ── Main event-loop ───────────────────────────────────────────────────────
async def main():
    # Expose /metrics before connecting so Prom doesn't scrape an empty target
    start_http_server(METRICS_PORT)
    log.info("Prometheus metrics on :%s/metrics", METRICS_PORT)
    
    # Check LLM proxy health
    llm_proxy_healthy = await check_llm_proxy_health()
    if not llm_proxy_healthy:
        log.warning("⚠️ LLM proxy not responding - proceeding anyway, but expect delays or errors")

    # JetStream pull-loop → on_request (runs forever)
    await consume(on_request)


if __name__ == "__main__":
    asyncio.run(main())