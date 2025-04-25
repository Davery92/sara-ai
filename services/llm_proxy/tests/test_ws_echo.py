import pytest
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport

transport = ASGITransport(app=app)
@pytest.mark.asyncio
async with AsyncClient(transport=transport, base_url="http://test") as ac:
    async with ac.websocket_connect("/v1/stream") as ws:
            await ws.send_json({"model": "qwen", "messages": [{"role": "user", "content": "ping"}]})
            chunk = await ws.receive_json()
            assert "delta" in chunk