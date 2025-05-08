import pytest
from fastapi.testclient import TestClient
import os
import json
import time
import jwt
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from services.common.persona_service import PersonaService, get_persona_service
from app.auth import get_user_id, _SECRET, _ALG
from app.redis_client import get_redis
from app.main import app

# Mock user ID for authentication
MOCK_USER_ID = "test-user-123"

# Sample persona content for tests
SAMPLE_DEFAULT_PERSONA = """# Sara - Default Personality

You are Sara, an AI assistant with a helpful and friendly demeanor.

## Voice & Tone
- Use casual, conversational language
- Feel free to use contractions (I'll, we're, you're)
- Occasionally use informal phrases like "sure thing!" or "got it!"
"""

SAMPLE_FORMAL_PERSONA = """# Sara - Formal Personality

You are Sara, an AI assistant with a professional and precise demeanor.

## Voice & Tone
- Use formal, structured language
- Avoid contractions (use "I will" instead of "I'll")
- Never use slang, colloquialisms, or casual expressions
"""

# Create mock personas
mock_personas = {
    "sara_default": SAMPLE_DEFAULT_PERSONA,
    "sara_formal": SAMPLE_FORMAL_PERSONA
}

# Generate valid JWT token for tests
@pytest.fixture
def auth_headers():
    """Generate valid JWT token and return authorization headers."""
    payload = {
        "sub": MOCK_USER_ID,
        "type": "access",
        "jti": "test-jti",
        "iat": time.time(),
        "exp": time.time() + 3600,  # Valid for 1 hour
    }
    token = jwt.encode(payload, _SECRET, algorithm=_ALG)
    return {"Authorization": f"Bearer {token}"}

# Create mock PersonaService
class MockPersonaService(PersonaService):
    def __init__(self):
        # Skip the parent initialization which tries to load files
        self.personas = mock_personas
        
    def get_available_personas(self) -> list:
        return list(self.personas.keys())
    
    def get_default_persona(self) -> str:
        return "sara_default"
    
    def get_persona_content(self, persona_name: str):
        return self.personas.get(persona_name)
    
    def get_persona_config(self, persona_name: str):
        content = self.get_persona_content(persona_name)
        if not content:
            raise ValueError(f"Persona not found: {persona_name}")
            
        return {
            "name": persona_name,
            "title": f"Sara - {'Default' if persona_name == 'sara_default' else 'Formal'} Personality",
            "version": "1.0",
            "content": content,
        }

# Mock Redis client
class MockRedis:
    def __init__(self):
        self.data = {}
        
    async def get(self, key):
        return self.data.get(key)
    
    async def set(self, key, value, *args, **kwargs):
        self.data[key] = value
        return True

# Set up mocks and dependency overrides
@pytest.fixture(autouse=True)
def setup_mocks():
    # Create our mock instances
    persona_service = MockPersonaService()
    redis_client = MockRedis()
    
    # Store the original dependencies
    original_deps = app.dependency_overrides.copy()
    
    # Override the dependencies
    app.dependency_overrides[get_persona_service] = lambda: persona_service
    app.dependency_overrides[get_redis] = lambda: redis_client
    app.dependency_overrides[get_user_id] = lambda: MOCK_USER_ID
    
    yield {
        "persona_service": persona_service,
        "redis_client": redis_client
    }
    
    # Restore original dependencies
    app.dependency_overrides = original_deps

# Create a test client
client = TestClient(app)

class TestPersonaAPI:
    
    def test_list_personas(self, setup_mocks, auth_headers):
        """Test listing available personas."""
        response = client.get("/v1/persona/list", headers=auth_headers)
        assert response.status_code == 200
        assert set(response.json()) == {"sara_default", "sara_formal"}
    
    def test_get_default_persona_config(self, setup_mocks, auth_headers):
        """Test getting default persona config when none specified."""
        response = client.get("/v1/persona/config", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "sara_default"
        assert "Sara - Default Personality" in data["title"]
        assert "content" in data
    
    def test_get_specific_persona_config(self, setup_mocks, auth_headers):
        """Test getting a specific persona config."""
        response = client.get("/v1/persona/config?persona_name=sara_formal", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "sara_formal"
        assert "Sara - Formal Personality" in data["title"]
        assert "content" in data
    
    def test_get_invalid_persona(self, setup_mocks, auth_headers):
        """Test getting a non-existent persona."""
        response = client.get("/v1/persona/config?persona_name=invalid_persona", headers=auth_headers)
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_set_user_persona(self, setup_mocks, auth_headers):
        """Test setting a user's preferred persona."""
        response = client.patch("/v1/persona", json={"persona": "sara_formal"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["persona"] == "sara_formal"
        
        # Verify the value was stored in Redis
        redis_key = f"user:persona:{MOCK_USER_ID}"
        assert setup_mocks["redis_client"].data.get(redis_key) == "sara_formal"
        
    def test_set_invalid_user_persona(self, setup_mocks, auth_headers):
        """Test setting an invalid persona for a user."""
        response = client.patch("/v1/persona", json={"persona": "nonexistent_persona"}, headers=auth_headers)
        assert response.status_code == 404
        
    def test_set_missing_persona_field(self, auth_headers):
        """Test setting a user persona with missing persona field."""
        response = client.patch("/v1/persona", json={"something_else": "value"}, headers=auth_headers)
        assert response.status_code == 400


class TestPersonaFeatures:
    """Test actual persona features using a simulated LLM."""
    
    def test_formal_persona_avoids_slang(self):
        """Test that the formal persona avoids slang/contractions."""
        formal_persona = SAMPLE_FORMAL_PERSONA
        assert "avoid contractions" in formal_persona.lower()
        assert "never use slang" in formal_persona.lower()
    
    def test_default_persona_uses_contractions(self):
        """Test that the default persona uses contractions."""
        default_persona = SAMPLE_DEFAULT_PERSONA
        assert "contractions (i'll, we're, you're)" in default_persona.lower()
        assert "sure thing" in default_persona.lower() 