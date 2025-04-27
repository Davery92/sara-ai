import pytest
from httpx import AsyncClient
from services.gateway.app.main import app
from services.gateway.app.auth import login, verify
from fastapi.testclient import TestClient
from services.gateway.main import app

client = TestClient(app)

def test_login_roundtrip():
    tokens = login("alice")
    assert "access_token" in tokens

    hdr = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = client.get("/auth/me", headers=hdr)
    assert r.status_code == 200
    assert r.json()["user"] == "alice"



@pytest.mark.asyncio
async def test_auth_stub_allows_request():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        r = await ac.get("/healthz", headers={"Authorization": "Bearer foo"})
    assert r.status_code == 200
