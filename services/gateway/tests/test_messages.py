import pytest
import time
import jwt
from services.gateway.app.main import app
from httpx import AsyncClient
from services.gateway.app.auth import _SECRET, _ALG

@pytest.mark.asyncio
async def test_message_persistence():
    # Generate a valid token directly instead of trying to login
    payload = {
        "sub": "demo-user",
        "type": "access",
        "jti": "test-jti",
        "iat": time.time(),
        "exp": time.time() + 3600,  # Valid for 1 hour
    }
    token = jwt.encode(payload, _SECRET, algorithm=_ALG)
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Use the token we created
        headers = {"Authorization": f"Bearer {token}"}
        
        # Create message - using the correct route
        r = await client.post("/messages/", json={"text":"it works!"}, headers=headers)
        assert r.status_code == 201, r.text  # Status code is 201 CREATED
        data = r.json()
        assert data["text"] == "it works!"
        assert "status" in data
        assert data["status"] == "queued"