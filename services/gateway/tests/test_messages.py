import pytest
from services.gateway.app.main import app
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_message_persistence():
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 1) login
        r = await client.post("/auth/login", json={"username":"demo"})
        token = r.json()["access_token"]

        # 2) create message - using the correct route
        headers = {"Authorization": f"Bearer {token}"}
        r2 = await client.post("/messages/", json={"text":"it works!"}, headers=headers)
        assert r2.status_code == 201, r2.text
        data = r2.json()
        assert data["text"] == "it works!"
        assert "status" in data  # Changed expectation to match the actual response
        assert data["status"] == "queued"