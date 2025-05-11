import uuid, json, os
from typing import Tuple
import nats

# Use localhost when running locally, container hostname when in container
#NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222" if os.getenv("ENV") != "prod" else "nats://nats:4222")
NATS_URL = os.getenv("NATS_URL", "nats://nats:4222")
def session_subjects() -> Tuple[str, str, str]:
    session_id = uuid.uuid4().hex
    req  = f"chat.request.{session_id}"
    resp = f"chat.reply.{session_id}"
    return session_id, req, resp

async def nats_connect():
    nc = nats.aio.client.Client()
    try:
        await nc.connect(servers=[NATS_URL])
        return nc
    except Exception as e:
        print(f"Error connecting to NATS: {e}")
        raise
