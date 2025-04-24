import pytest, asyncio
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_healthz():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True}
