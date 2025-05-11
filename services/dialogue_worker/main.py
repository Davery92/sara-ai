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
    """Stream LLM output to NATS; cancel if ACKs stop."""
    last_ack = time.monotonic()  # Initialize with current time
    ack_sid = None
    max_attempts = 3  # Maximum number of connection attempts

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
        while attempt <= max_attempts:  # Limit the number of attempts
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

                    try:
                        # Set larger timeout for initial connection
                        async with session.ws_connect(LLM_WS_URL, timeout=20) as ws:
                            log.info("✅ Successfully connected to LLM proxy websocket")
                            
                            # Send initial payload (this might take time for the LLM to process)
                            log.info("📤 Sending payload to LLM proxy")
                            # Reset the last_ack time right before sending payload
                            last_ack = time.monotonic()  # Reset timer before potentially long operation
                            await ws.send_json(payload)
                            log.info("📤 Payload sent, waiting for responses...")
                            
                            # Send an initial ACK to indicate we're still alive
                            await nc.publish(ack_subject, b"+INIT_ACK")
                            
                            # Get the first message with a timeout
                            try:
                                # Confirm LLM has started processing
                                first_msg = await asyncio.wait_for(ws.receive(), timeout=10.0)
                                log.info("📨 Received first message from LLM proxy")
                                
                                # Process the first message
                                if first_msg.type == aiohttp.WSMsgType.BINARY or first_msg.type == aiohttp.WSMsgType.TEXT:
                                    start = time.perf_counter()
                                    await nc.publish(
                                        reply_subject,
                                        first_msg.data if isinstance(first_msg.data, bytes) else first_msg.data.encode(),
                                    )
                                    WS_LATENCY.observe(time.perf_counter() - start)
                                    
                                    # Send first ACK to reset the timer
                                    await nc.publish(ack_subject, b"+ACK")
                                    counter = 1
                                else:
                                    log.warning(f"Unexpected first message type: {first_msg.type}")
                                    raise ValueError(f"Unexpected message type: {first_msg.type}")
                                
                            except asyncio.TimeoutError:
                                log.warning("⏰ Timed out waiting for first message from LLM proxy")
                                raise

                            # Continue with the rest of the stream
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
                                    log.info(f"📤 Sent ACK after {counter} chunks")

                                # ⏱️  Check for client heartbeat
                                time_since_last_ack = time.monotonic() - last_ack
                                if time_since_last_ack > ACK_TIMEOUT:
                                    # Only warn on first detection
                                    if time_since_last_ack < ACK_TIMEOUT + 2:  # Only log once
                                        log.warning(f"⚠️ No ACK for {time_since_last_ack:.1f}s – will cancel if no ACK in 5s")
                                        # Send an additional ACK to try to recover
                                        await nc.publish(ack_subject, b"+RECOVERY_ACK")
                                        
                                    # Only cancel after timeout + 5 seconds grace period
                                    if time_since_last_ack > ACK_TIMEOUT + 5:
                                        CANCELLED.inc()
                                        log.warning(f"❌ No ACK for {time_since_last_ack:.1f}s – cancelling stream")
                                        break
                            break  # Exit retry loop if successful
                    except aiohttp.ClientError as e:
                        log.warning(f"❌ WebSocket connection error: {str(e)}")
                        raise
                    except asyncio.TimeoutError:
                        log.warning("⏰ Timeout while communicating with LLM proxy")
                        raise
            except (ConnectionRefusedError, OSError) as e:
                log.warning(f"❌ LLM proxy not ready ({e}) - retrying in {delay}s (attempt {attempt}/{max_attempts})")
            except Exception as e:
                log.error(f"❌ Unexpected LLM proxy connection error: {str(e)} - retrying in {delay}s (attempt {attempt}/{max_attempts})")
                log.error(f"Error type: {type(e)}")
            await asyncio.sleep(delay)
            delay = min(delay * 2, max_delay)
            attempt += 1
            
        # If we've exhausted all attempts, send a fallback response
        if attempt > max_attempts:
            log.warning(f"⚠️ Exhausted {max_attempts} attempts to connect to LLM proxy - sending fallback response")
            fallback_message = {
                "role": "assistant",
                "content": "I'm sorry, but I'm having trouble connecting to my language model backend at the moment. Please try again in a few moments."
            }
            await nc.publish(reply_subject, json.dumps(fallback_message).encode())
            # Send an ACK to avoid client timeout
            await nc.publish(ack_subject, b"+ACK")
    finally:
        try:
            if ack_sid and nc and hasattr(nc, "unsubscribe"):
                await nc.unsubscribe(ack_sid)
        except Exception as e:
            log.warning(f"Error during unsubscribe: {str(e)}")


# ── NATS subscription callback ────────────────────────────────────────────
async def on_request(msg, nc):
    try:
        if not msg or not hasattr(msg, 'data'):
            log.error("Invalid message received: message object is None or missing data")
            return
            
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError as e:
            log.error(f"Failed to decode message data as JSON: {e}")
            return
            
        if not hasattr(msg, 'reply') or not msg.reply:
            log.error("Message missing reply subject")
            return
        
        reply_subject = msg.reply
        
        # Safe header access with default empty dict
        headers = getattr(msg, 'headers', {}) or {}
        ack_subject = headers.get("Ack", "")
        
        if not ack_subject:
            log.error("Missing Ack header – refusing request")
            return

        # Extract auth token
        auth_token = headers.get("Auth", "")
        if not auth_token:
            log.warning("Rejecting msg: missing Auth header")
            return

        # Enhance the prompt with persona and memories
        try:
            enhanced_payload = await enhance_prompt(payload, auth_token)
            await forward_to_llm_proxy(enhanced_payload, reply_subject, ack_subject, nc)
        except Exception as e:
            log.error(f"Error in processing or forwarding: {str(e)}")
            traceback.print_exc()
            
            # Try to send a fallback error message to the client
            try:
                error_msg = {
                    "role": "assistant",
                    "content": "I apologize, but I encountered an error while processing your request."
                }
                if reply_subject:
                    await nc.publish(reply_subject, json.dumps(error_msg).encode())
            except Exception as nested_error:
                log.error(f"Failed to send error response: {str(nested_error)}")
    except Exception as e:
        log.error(f"Error processing message: {str(e)}")
        traceback.print_exc()


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