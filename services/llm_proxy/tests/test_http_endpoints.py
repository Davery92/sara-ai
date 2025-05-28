import pytest
import httpx
import json
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from services.llm_proxy.app.main import app

client = TestClient(app)

class TestHTTPEndpoints:
    """Test the new HTTP endpoints for chat completions and embeddings"""
    
    def test_healthz_endpoint(self):
        """Test that the health check endpoint works"""
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "message": "LLM proxy service is running"}
    
    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_chat_completions_endpoint_success(self, mock_post):
        """Test successful chat completions request"""
        # Mock the Ollama response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "This is a test summary."
                    }
                }
            ]
        }
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Test payload
        payload = {
            "model": "qwen3:32b",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Summarize this text."}
            ],
            "temperature": 0.3,
            "max_tokens": 200
        }
        
        async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/v1/chat/completions", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "choices" in data
        assert data["choices"][0]["message"]["content"] == "This is a test summary."
    
    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_embeddings_endpoint_success(self, mock_post):
        """Test successful embeddings request"""
        # Mock the Ollama response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "data": [
                {
                    "embedding": [0.1, 0.2, 0.3, 0.4, 0.5]
                }
            ]
        }
        mock_post.return_value.__aenter__.return_value = mock_response
        
        # Test payload
        payload = {
            "model": "bge-m3",
            "input": "This is a test text for embedding."
        }
        
        async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/v1/embeddings", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"][0]["embedding"] == [0.1, 0.2, 0.3, 0.4, 0.5]
    
    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_chat_completions_endpoint_error(self, mock_post):
        """Test chat completions request with Ollama error"""
        # Mock the Ollama error response
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.json.return_value = {"error": "Internal server error"}
        mock_post.return_value.__aenter__.return_value = mock_response
        
        payload = {
            "model": "qwen3:32b",
            "messages": [
                {"role": "user", "content": "Test"}
            ]
        }
        
        async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/v1/chat/completions", json=payload)
        
        assert response.status_code == 500
    
    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_embeddings_endpoint_error(self, mock_post):
        """Test embeddings request with Ollama error"""
        # Mock the Ollama error response
        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.json.return_value = {"error": "Model not found"}
        mock_post.return_value.__aenter__.return_value = mock_response
        
        payload = {
            "model": "nonexistent-model",
            "input": "Test text"
        }
        
        async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/v1/embeddings", json=payload)
        
        assert response.status_code == 404
    
    def test_chat_completions_sets_stream_false(self):
        """Test that chat completions endpoint sets stream=False by default"""
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {"choices": [{"message": {"content": "test"}}]}
            mock_post.return_value.__aenter__.return_value = mock_response
            
            payload = {
                "model": "qwen3:32b",
                "messages": [{"role": "user", "content": "test"}]
            }
            
            response = client.post("/v1/chat/completions", json=payload)
            
            # Verify that the call to Ollama included stream=False
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            sent_payload = call_args[1]['json']
            assert sent_payload['stream'] is False 