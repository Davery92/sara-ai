import pytest
from unittest.mock import AsyncMock, patch
from app.utils.save_chat_chunk import save_chat_chunk

@pytest.mark.asyncio
async def test_save_chat_chunk_calls_push_and_nats(redis_mock):
    """Test that save_chat_chunk correctly calls push_chat_chunk and publishes to NATS."""
    with patch("app.utils.save_chat_chunk.push_chat_chunk", new=AsyncMock()) as mock_push, \
         patch("app.utils.save_chat_chunk.NATS") as mock_nats:
        mock_nc = AsyncMock()
        mock_nats.return_value = mock_nc
        mock_nc.connect.return_value = None
        mock_nc.publish.return_value = None
        mock_nc.drain.return_value = None

        await save_chat_chunk("room2", "user", "test message")
        
        # Verify the function correctly interacts with Redis and NATS
        mock_push.assert_awaited_once()
        mock_nc.connect.assert_awaited_once()
        mock_nc.publish.assert_awaited()
        mock_nc.drain.assert_awaited_once()

@pytest.mark.asyncio
async def test_save_chat_chunk_formats_message_correctly(redis_mock):
    """Test that save_chat_chunk correctly formats the chunk with all required fields."""
    with patch("app.utils.save_chat_chunk.push_chat_chunk", new=AsyncMock()) as mock_push, \
         patch("app.utils.save_chat_chunk.NATS") as mock_nats, \
         patch("uuid.uuid4", return_value="test-uuid"):
        mock_nc = AsyncMock()
        mock_nats.return_value = mock_nc
        mock_nc.connect.return_value = None
        mock_nc.publish.return_value = None
        mock_nc.drain.return_value = None

        room_id = "test-room"
        role = "user"
        text = "Hello, world!"
        
        await save_chat_chunk(room_id, role, text)
        
        # Check the chunk passed to push_chat_chunk
        call_args = mock_push.await_args[0]
        assert call_args[0] == room_id
        
        chunk = call_args[1]
        assert chunk["id"] == "test-uuid"
        assert chunk["room_id"] == room_id
        assert chunk["role"] == role
        assert chunk["text"] == text
        assert "ts" in chunk  # Timestamp should be present 