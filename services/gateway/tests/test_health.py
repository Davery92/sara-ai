import pytest, asyncio
from httpx import AsyncClient
from services.gateway.app.main import app
from fastapi.testclient import TestClient
from services.gateway.main import app

def test_healthz():
    c = TestClient(app)
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True

@pytest.mark.asyncio
async def test_healthz():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/healthz")
    assert r.status_code == 200 and r.json() == {"ok": True}
