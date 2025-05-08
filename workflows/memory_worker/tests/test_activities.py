import pytest
import pytest_asyncio  # Explicitly import it
import httpx
import json
import uuid
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os
import importlib

# Make sure we import the activities module directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our activities module
import activities

# Mark all tests as async
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_redis():
    redis_mock = AsyncMock()
    redis_mock.keys.return_value = [b"room:123:messages", b"room:456:messages"]
    redis_mock.lrange.return_value = [
        json.dumps({"text": "Hello, how are you?", "user": "user1"}).encode(),
        json.dumps({"text": "I'm doing great!", "user": "user2"}).encode(),
    ]
    redis_mock.delete.return_value = True
    return redis_mock

@pytest.fixture
def mock_async_session():
    """Create a mock async session that works with the context manager"""
    session_mock = AsyncMock()
    session_mock.commit = AsyncMock()
    
    # Create a mock context manager that returns the session
    async_session_ctx = AsyncMock()
    async_session_ctx.__aenter__.return_value = session_mock
    async_session_ctx.__aexit__.return_value = None
    
    # Create a factory that returns the context manager
    session_factory = MagicMock(return_value=async_session_ctx)
    
    return session_factory, session_mock

# Separate mocks for each API endpoint to handle specific cases
@pytest.fixture
def mock_summary_response():
    resp = AsyncMock()
    resp.raise_for_status = AsyncMock(return_value=None)  # Ensure this is awaited
    resp.json = AsyncMock(return_value={
        "choices": [
            {"message": {"content": "This is a test summary."}}
        ]
    })
    return resp

@pytest.fixture
def mock_embedding_response():
    resp = AsyncMock()
    resp.raise_for_status = AsyncMock(return_value=None)  # Ensure this is awaited
    resp.json = AsyncMock(return_value={
        "data": [
            {"embedding": [0.1] * 1024}
        ]
    })
    return resp

async def test_list_rooms_with_hot_buffer(mock_redis):
    with patch("activities.get_redis", return_value=mock_redis):
        result = await activities.list_rooms_with_hot_buffer()
        assert result == ["123", "456"]
        mock_redis.keys.assert_called_once_with("room:*:messages")

async def test_fetch_buffer(mock_redis):
    with patch("activities.get_redis", return_value=mock_redis):
        result = await activities.fetch_buffer("123")
        assert len(result) == 2
        assert result[0]["text"] == "I'm doing great!"
        assert result[1]["text"] == "Hello, how are you?"
        mock_redis.lrange.assert_called_once_with("room:123:messages", 0, -1)

async def test_call_llm_summary(mock_summary_response):
    # Directly patch the client context manager's return value and post method
    client = AsyncMock()
    client.post.return_value = mock_summary_response
    
    # Create a context manager that returns our client
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    
    # Patch the AsyncClient constructor to return our context manager
    with patch("httpx.AsyncClient", return_value=cm):
        result = await activities.call_llm_summary("Test conversation")
        assert result == "This is a test summary."
        # Check the call was made with the right model
        client.post.assert_called()
        call_args = client.post.call_args
        assert "json" in call_args[1]
        assert call_args[1]["json"]["model"] == activities.SUMMARY_MODEL

async def test_get_embedding(mock_embedding_response):
    # Directly patch the client context manager's return value and post method
    client = AsyncMock()
    client.post.return_value = mock_embedding_response
    
    # Create a context manager that returns our client
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    
    # Patch the AsyncClient constructor to return our context manager
    with patch("httpx.AsyncClient", return_value=cm):
        result = await activities.get_embedding("Test text")
        assert len(result) == 1024
        assert result[0] == 0.1
        # Check the call was made with the right model
        client.post.assert_called()
        call_args = client.post.call_args
        assert "json" in call_args[1]
        assert call_args[1]["json"]["model"] == activities.EMBEDDING_MODEL

async def test_summarise_texts_success():
    chunks = [
        {"text": "Hello, how are you?"},
        {"text": "I'm doing great!"}
    ]
    with patch("activities.call_llm_summary", return_value="This is a summary."):
        result = await activities.summarise_texts(chunks)
        assert result == "This is a summary."

async def test_summarise_texts_failure():
    chunks = [
        {"text": "Hello, how are you?"},
        {"text": "I'm doing great!"}
    ]
    with patch("activities.call_llm_summary", side_effect=Exception("API error")):
        result = await activities.summarise_texts(chunks)
        assert "Conversation with 2 messages" in result

async def test_upsert_summary(mock_async_session, mock_redis):
    session_factory, session_mock = mock_async_session
    
    with patch("activities.AsyncSessionLocal", session_factory), \
         patch("activities.get_redis", return_value=mock_redis), \
         patch("activities.upsert_memory") as mock_upsert:
        
        await activities.upsert_summary("123", "Test summary", [0.1] * 1024)
        
        mock_upsert.assert_called_once()
        assert mock_upsert.call_args[1]["room_id"] == "123"
        assert mock_upsert.call_args[1]["text"] == "Test summary"
        mock_redis.delete.assert_called_once_with("room:123:messages") 