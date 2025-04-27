# services/gateway/tests/conftest.py

import pytest

# Simple mock Redis for testing
@pytest.fixture
def mock_redis(monkeypatch):
    """Mock Redis for tests"""
    class MockRedis:
        def __init__(self):
            self.store = {}
            
        async def get(self, key):
            return self.store.get(key)
            
        async def set(self, key, value, ex=None):
            self.store[key] = value
            
        async def close(self):
            pass
    
    mock = MockRedis()
    
    async def mock_get_redis():
        return mock
    
    from services.gateway.app import redis_client
    monkeypatch.setattr(redis_client, "get_redis", mock_get_redis)
    return mock