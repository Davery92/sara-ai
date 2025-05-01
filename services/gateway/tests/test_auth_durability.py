import jwt, httpx, asyncio
from nats.aio.client import Client as NATS

BAD = jwt.encode({"sub": "anon", "exp": 0}, "wrong", algorithm="HS256")

async def test_bad_jwt_rejected():
    nc = NATS(); await nc.connect("nats://nats:4222")
    js = nc.jetstream()
    await js.publish("chat.request.test", b"hi", headers={"Auth": BAD})
    async with httpx.AsyncClient() as c:
        await asyncio.sleep(0.5)                     # give DW a beat
        r = await c.get("http://dialogue_worker:8000/metrics")
    assert "dw_auth_fail_total" in r.text
