import os, uuid, asyncio, json, logging, time
from nats.aio.client import Client as NATS
from .redis_utils import push_chat_chunk 

ACK_EVERY = int(os.getenv("ACK_EVERY", 10))   # send an ACK every N chunks
RAW_SUBJECT = os.getenv("RAW_MEMORY_SUBJECT", "memory.raw")
log = logging.getLogger("gateway.nats")

class GatewayNATS:
    def __init__(self, url: str):
        self.nc = NATS()
        self.url = url

    async def start(self):
        await self.nc.connect(servers=[self.url])

    async def stream_request(self, req_subject: str, payload: dict, ws):
        """Publish a chat request and relay the response stream to the client WS."""
        reply_subject = f"resp.{uuid.uuid4().hex}"
        ack_subject   = f"inbox.{uuid.uuid4().hex}"

        # 1⃣ subscribe to both reply & ack subjects
        async def on_chunk(msg):
            # decode once
            chunk_json = msg.data.decode()

            # 👉 1. stream to browser
            await ws.send_text(chunk_json)

            # 👉 2. stuff into Redis hot buffer  (summary roll‑up will fetch)
            try:
                chunk = json.loads(chunk_json)
                await push_chat_chunk(chunk["room_id"], chunk)
            except Exception as e:
                log.warning("failed to cache chunk in redis: %s", e)

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
            reply=reply_subject,
            headers={"Ack": ack_subject.encode()}
        )
       
        await push_chat_chunk(payload["room_id"], payload)
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
