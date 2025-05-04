import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_refresh_and_blacklist(redis_mock, anyio_backend):
    """Test that refresh tokens get blacklisted after use."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 1. login
        r = await client.post("/auth/login", json={"username": "alice"})
        assert r.status_code == 200
        tokens = r.json()
        
        # 2. refresh succeeds
        r2 = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert r2.status_code == 200
        new_tokens = r2.json()
        assert new_tokens["access_token"] != tokens["access_token"]
        
        # 3. re-use old refresh → 401
        r3 = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert r3.status_code == 401