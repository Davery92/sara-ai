import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_auth_stub_allows_request():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/healthz", headers={"Authorization": "Bearer foo"})
    assert r.status_code == 200
