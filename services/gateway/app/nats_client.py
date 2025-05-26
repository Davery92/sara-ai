import os, uuid, asyncio, json, logging, time
from nats.aio.client import Client as NATS
from .redis_utils import push_unified_user_memory

ACK_EVERY = int(os.getenv("ACK_EVERY", 10))   # send an ACK every N chunks
RAW_SUBJECT = os.getenv("RAW_MEMORY_SUBJECT", "memory.raw")
log = logging.getLogger("gateway.nats")

class GatewayNATS:
    def __init__(self, url: str):
        self.nc = NATS()
        self.url = url

    async def start(self, max_retries: int = 5, delay: float = 2.0):
        """Connect to NATS with retries and exponential backoff."""
        for attempt in range(1, max_retries + 1):
            try:
                await self.nc.connect(servers=[self.url])
                log.info(f"✅ Connected to NATS on attempt {attempt}")
                return
            except Exception as e:
                log.warning(f"❌ NATS connection attempt {attempt} failed: {e}")
                if attempt == max_retries:
                    log.error("❌ Max retries exceeded – unable to connect to NATS")
                    raise
                await asyncio.sleep(delay * attempt)  # exponential-ish backoff


    async def stream_request(self, req_subject: str, payload: dict, ws):
        """Publish a chat request and relay the response stream to the client WS."""
        reply_subject = f"resp.{uuid.uuid4().hex}"
        ack_subject   = f"inbox.{uuid.uuid4().hex}"

        # Extract user_id from the initial payload for use in on_chunk if needed
        # Assuming user_id is consistently available in the top-level payload
        initial_user_id = payload.get("user_id")
        if not initial_user_id:
            log.error(f"CRITICAL: user_id missing in initial payload for stream_request. Payload: {str(payload)[:200]}")
            # Decide handling: raise error, or try to proceed without Redis push for assistant?
            # For now, we'll log and let it potentially fail later if user_id is vital.

        # 1⃣ subscribe to both reply & ack subjects
        async def on_chunk(msg):
            # decode once
            chunk_json = msg.data.decode()

            # 👉 1. stream to browser
            await ws.send_text(chunk_json)

            # 👉 2. stuff into Redis hot buffer (summary roll‑up will fetch)
            try:
                chunk = json.loads(chunk_json)
                # Assuming chunk structure is similar to what push_unified_user_memory expects
                # e.g., {"user_id": "...", "room_id": "...", "role": "assistant", "text": "...", ...}
                # The chunk received here is the assistant's reply part.
                
                chunk_user_id = chunk.get("user_id", initial_user_id) # Prefer user_id from chunk, fallback to initial
                chunk_room_id = chunk.get("room_id")
                chunk_role = chunk.get("role", "assistant") # Role might be in the chunk, or assume assistant
                chunk_text = chunk.get("text") # Or extract from "choices.[0].delta.content" if it's raw LLM output

                # More robust extraction for typical LLM stream chunk:
                if not chunk_text and "choices" in chunk and chunk["choices"]:
                    delta = chunk["choices"][0].get("delta", {})
                    if "content" in delta:
                        chunk_text = delta["content"]
                
                if chunk_user_id and chunk_room_id and chunk_role and chunk_text is not None: # Ensure text can be empty string but not None
                    await push_unified_user_memory(
                        user_id=str(chunk_user_id), 
                        room_id=str(chunk_room_id), 
                        role=chunk_role, 
                        text=chunk_text
                    )
                else:
                    log.warning(f"Skipping Redis push for assistant chunk due to missing data. user_id: {chunk_user_id}, room_id: {chunk_room_id}, role: {chunk_role}, has_text: {chunk_text is not None}. Chunk: {str(chunk)[:200]}")

            except Exception as e:
                log.warning(f"Failed to cache assistant chunk in unified redis: {e}. Chunk: {chunk_json[:200]}", exc_info=True)

            # 👉 3. (optional) fan‑out to embedding_worker so assistant
            #      replies land in Postgres too
            try:
                await self.nc.publish(RAW_SUBJECT, msg.data)
            except Exception as e:
                log.warning("failed to fwd chunk to %s: %s", RAW_SUBJECT, e)

        async def on_ack(msg):
            pass  # we don't need the body – just receipt means worker is alive

        sid_chunk = await self.nc.subscribe(reply_subject, cb=on_chunk)
        sid_ack   = await self.nc.subscribe(ack_subject,  cb=on_ack)

        # 2⃣ publish the request with Ack header
        await self.nc.publish(
            req_subject,
            json.dumps(payload).encode(),
            headers={
                "Ack":   ack_subject,
                "Reply": reply_subject   # keep this, worker relies on it
            }
        )
       
        # This was pushing the *user's initial message* (payload) to Redis.
        # The payload structure should have: user_id, room_id, role="user", msg="text"
        user_message_user_id = payload.get("user_id")
        user_message_room_id = payload.get("room_id")
        user_message_role = payload.get("role", "user") # Should be 'user' from client
        user_message_text = payload.get("msg") # 'msg' is typical for user's text

        if user_message_user_id and user_message_room_id and user_message_role and user_message_text is not None:
            await push_unified_user_memory(
                user_id=str(user_message_user_id), 
                room_id=str(user_message_room_id), 
                role=user_message_role, 
                text=user_message_text
            )
            log.info(f"Pushed initial user message to unified Redis. User: {user_message_user_id}, Room: {user_message_room_id}")
        else:
            log.warning(f"Skipping Redis push for initial user message due to missing data. Payload: {str(payload)[:200]}")

        await self.nc.publish(RAW_SUBJECT, json.dumps(payload).encode())
        # 3⃣ relay chunks until WS closes or worker stops
        chunk_counter = 0
        try:
            while True:
                await asyncio.sleep(0.01)     # back-off the event-loop
                if ws.closed:
                    log.warning("client closed early – cancelling stream")
                    break
        finally:
            await self.nc.unsubscribe(sid_chunk)
            await self.nc.unsubscribe(sid_ack)
            # no need to send a final message; Dialogue-Worker will see our absence
