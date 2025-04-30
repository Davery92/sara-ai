import uuid, json, os
from typing import Tuple
import nats

NATS_URL = os.getenv("NATS_URL", "nats://nats:4222")

def session_subjects() -> Tuple[str, str, str]:
    session_id = uuid.uuid4().hex
    req  = f"chat.request.{session_id}"
    resp = f"chat.reply.{session_id}"
    return session_id, req, resp

async def nats_connect():
    nc = nats.aio.client.Client()
    await nc.connect(servers=[NATS_URL])
    return nc
