import os
import sys
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Dict, Any, Optional, List
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import UUID, uuid4
from httpx import ASGITransport, AsyncClient
from pathlib import Path

# Add the project root to the path so imports work correctly
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the application with correct paths
from services.gateway.app.main import app
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ----- MOCK CLASSES -----

# Mock Redis
class MockRedis:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
        self.expiry: Dict[str, float] = {}
    
    async def ping(self):
        """Mock ping command."""
        return True
    
    async def get(self, key: str) -> Optional[str]:
        """Mock get command."""
        return self.data.get(key)
    
    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Mock set command with optional expiry."""
        self.data[key] = value
        if ex is not None:
            self.expiry[key] = ex
        return True
    
    async def delete(self, *keys: str) -> int:
        """Mock delete command."""
        count = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                if key in self.expiry:
                    del self.expiry[key]
                count += 1
        return count

# Mock for SQLAlchemy objects
class MockOrder:
    """Mock for SQLAlchemy order_by clause."""
    def __init__(self, clause):
        self.clause = clause

# Mock Vector class for pgvector
class MockVector:
    """Mock for pgvector Vector class."""
    def __init__(self, dim):
        self.dim = dim
    
    def __call__(self, embedding=None):
        """Constructor for Vector instances."""
        if embedding is None:
            return [0.0] * self.dim
        return embedding
    
    def op(self, operator):
        """Mock for vector operators like <->"""
        def inner_op(other):
            # Just return a mock for testing
            return MagicMock()
        return inner_op

# Mock database classes
class MockColumn:
    """Mock for SQLAlchemy Column."""
    def __init__(self, name, type_=None, *args, **kwargs):
        self.name = name
        self.type = type_
    
    def __eq__(self, other):
        return MagicMock()
    
    def __ne__(self, other):
        return MagicMock()
    
    def op(self, operator):
        def inner_op(other):
            return MagicMock()
        return inner_op

class MockResult:
    """Mock result from database query."""
    def __init__(self, rows=None):
        self.rows = rows or []
    
    def all(self):
        """Return all rows."""
        return self.rows

class _TestRow:
    """Mock row for test results."""
    def __init__(self, id, text):
        self.id = id
        self.text = text

class MockAsyncSession:
    """Enhanced mock for AsyncSession with search support."""
    def __init__(self):
        self.messages = []
        # Add some test data
        self.messages.append({
            "id": uuid4(),
            "text": "This is a test message",
            "embedding": [0.1] * 1024
        })
        self.messages.append({
            "id": uuid4(),
            "text": "Another test message for search",
            "embedding": [0.2] * 1024
        })
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    async def execute(self, stmt):
        """Execute statement with special handling for search queries."""
        # For any query, return our test data
        limit = 5
        if hasattr(stmt, '_limit_clause') and stmt._limit_clause is not None:
            limit = stmt._limit_clause.value
        
        result = []
        for msg in self.messages[:limit]:
            result.append(_TestRow(msg["id"], msg["text"]))
        return MockResult(result)
    
    async def commit(self):
        pass
    
    async def rollback(self):
        pass

# ----- FIXTURES -----

# Redis mock fixture
@pytest_asyncio.fixture
async def redis_mock():
    """Fixture that patches the Redis client with a mock implementation."""
    # Create mock instance
    mock_redis = MockRedis()
    
    # Import and patch the get_redis function with correct paths
    from services.gateway.app.redis_client import get_redis as original_get_redis
    
    # Create patched function
    async def mock_get_redis():
        return mock_redis
    
    # Apply patch
    import services.gateway.app.redis_client
    services.gateway.app.redis_client.get_redis = mock_get_redis
    
    # If there are other modules importing get_redis directly, patch those too
    try:
        import services.gateway.app.auth
        services.gateway.app.auth.get_redis = mock_get_redis
    except (ImportError, AttributeError):
        pass
    
    yield mock_redis
    
    # Restore original function after test
    services.gateway.app.redis_client.get_redis = original_get_redis

# Mock embeddings function
@pytest_asyncio.fixture
async def mock_embeddings(monkeypatch):
    """Fixture that mocks the embeddings computation."""
    # Direct approach: patch the function
    async def mock_compute_embedding(text):
        """Return a fixed embedding vector."""
        return [0.1] * 1024
    
    # Apply patch with corrected imports
    from services.gateway.app.utils import embeddings
    original_compute_embedding = embeddings.compute_embedding
    monkeypatch.setattr(embeddings, "compute_embedding", mock_compute_embedding)
    
    # Also mock httpx for good measure
    mock_response = AsyncMock()
    mock_response.raise_for_status = AsyncMock()
    mock_response.json.return_value = {
        "data": [{"embedding": [0.1] * 1024}]
    }
    
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = AsyncMock()
    mock_client.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
    
    import httpx
    original_async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: mock_client)
    
    yield
    
    # Restore originals
    monkeypatch.setattr(embeddings, "compute_embedding", original_compute_embedding)
    monkeypatch.setattr(httpx, "AsyncClient", original_async_client)

# Database session fixture
@pytest_asyncio.fixture
async def db_session():
    """Fixture that provides an enhanced mocked database session."""
    session = MockAsyncSession()
    yield session

# Override get_session dependency
@pytest_asyncio.fixture
async def override_get_session(db_session):
    """Override the get_session dependency."""
    # Create override function
    async def mock_get_session():
        yield db_session
    
    # Apply override with corrected imports
    from services.gateway.app.db.session import get_session
    original_get_session = app.dependency_overrides.get(get_session, get_session)
    app.dependency_overrides[get_session] = mock_get_session
    
    yield
    
    # Restore original
    if original_get_session == get_session:
        del app.dependency_overrides[get_session]
    else:
        app.dependency_overrides[get_session] = original_get_session

# Mock pgvector modules
@pytest.fixture(autouse=True)
def mock_pgvector():
    """Mock pgvector modules globally."""
    # Create a complete mock for pgvector.sqlalchemy
    mock_vector_module = MagicMock()
    mock_vector_module.Vector = MockVector
    
    # Apply module mocks
    sys.modules['pgvector'] = MagicMock()
    sys.modules['pgvector.sqlalchemy'] = mock_vector_module
    
    # Also patch the Message model's embedding attribute with corrected imports
    with patch('services.gateway.app.db.models.Vector', MockVector):
        from services.gateway.app.db.models import Message
        original_embedding = Message.embedding
        
        # Create a mockable embedding attribute
        mock_embedding = MagicMock()
        mock_embedding.op = lambda op: (lambda other: MagicMock())
        Message.embedding = mock_embedding
        
        yield
        
        # Restore original
        Message.embedding = original_embedding

# Configure environment variables
@pytest.fixture(autouse=True)
def env_setup(monkeypatch):
    """Setup environment variables for tests."""
    monkeypatch.setenv("JWT_SECRET", "test-secret-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434")
    # Add other environment variables as needed

# Set anyio backend
@pytest.fixture
def anyio_backend():
    return "trio"

# New fixture for testing with httpx
@pytest_asyncio.fixture
async def httpx_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client