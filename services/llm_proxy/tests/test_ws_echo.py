import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from llm_proxy.app.main import app

@patch('llm_proxy.app.main.stream_completion')
def test_ws_roundtrip(mock_stream_completion):
    # Mock the stream_completion to return predictable chunks
    async def mock_stream():
        yield {"content": "Hello", "done": False}
        yield {"content": " world!", "done": True}
    
    mock_stream_completion.return_value = mock_stream()
    
    client = TestClient(app)
    with client.websocket_connect("/v1/stream") as websocket:
        # Send test payload
        test_payload = {
            "model": "test-model",
            "prompt": "Hello, world!",
            "stream": True
        }
        websocket.send_json(test_payload)
        
        # Receive first chunk
        chunk1 = websocket.receive_json()
        assert chunk1 == {"content": "Hello", "done": False}
        
        # Receive second chunk
        chunk2 = websocket.receive_json()
        assert chunk2 == {"content": " world!", "done": True}