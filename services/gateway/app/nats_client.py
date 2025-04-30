import os, uuid, asyncio, json, logging, time
from nats.aio.client import Client as NATS

ACK_EVERY = int(os.getenv("ACK_EVERY", 10))   # send an ACK every N chunks

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
            await ws.send_text(msg.data.decode())

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
