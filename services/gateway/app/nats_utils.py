import os, jwt, datetime
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext

JWT_SECRET = os.getenv("JWT_SECRET")

async def publish_chat(js, subj: str, payload: bytes, jwt_raw: str | None):
    hdrs = {"Auth": jwt_raw} if jwt_raw else {}
    await js.publish(subj, payload, headers=hdrs)

