# llm_proxy/tests/test_ws_echo.py

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from llm_proxy.app.main import app

#@pytest.mark.asyncio
async def test_ws_roundtrip():
    """Test the WebSocket endpoint with mocked Temporal client"""
    
    # Create a mock Temporal client
    mock_temporal_client = AsyncMock()
    mock_handle = AsyncMock()
    mock_handle.result.return_value = {
        "response": "Test response",
        "done": True
    }
    mock_temporal_client.start_workflow.return_value = mock_handle
    
    # Patch the temporal_client in the main module
    with patch('llm_proxy.app.main.temporal_client', mock_temporal_client):
        client = TestClient(app)
        
        with client.websocket_connect("/v1/stream") as websocket:
            # Send test data
            test_data = {
                "model": "llama2",
                "prompt": "Hello, world!",
                "stream": False
            }
            websocket.send_json(test_data)
            
            # Receive response
            response = websocket.receive_json()
            
            # Assert response
            assert response["response"] == "Test response"
            assert response["done"] == True
            
            # Assert that the workflow was started with correct parameters
            mock_temporal_client.start_workflow.assert_called_once()
            args = mock_temporal_client.start_workflow.call_args
            assert args[0][0] == "LLMWorkflow"
            assert args[1]["args"] == ["llama2", "Hello, world!", False]
            assert args[1]["task_queue"] == "llm-queue"