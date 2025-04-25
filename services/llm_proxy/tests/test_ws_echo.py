import pytest
from httpx import AsyncClient
from services.llm_proxy.app.main import app

@pytest.mark.asyncio
async def test_ws_roundtrip():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        async with ac.websocket_connect("/v1/stream") as ws:
            await ws.send_json({"model": "qwen", "messages": [{"role": "user", "content": "ping"}]})
            chunk = await ws.receive_json()
            assert "delta" in chunk