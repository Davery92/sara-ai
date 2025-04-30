import os, jwt, datetime
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext

JWT_SECRET = os.getenv("JWT_SECRET")

async def publish_chat(js: JetStreamContext, subj: str, payload: bytes, jwt_raw: str):
    """
    Push a chat request onto JetStream with the client's JWT in 'Auth' header.
    """
    hdrs = {"Auth": jwt_raw}
    await js.publish(subj, payload, headers=hdrs)
