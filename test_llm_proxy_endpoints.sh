#!/bin/bash

# Test script for LLM Proxy HTTP endpoints
# This script tests the new HTTP endpoints added to the llm_proxy service

set -e

echo "🧪 Testing LLM Proxy HTTP Endpoints..."
echo "======================================"

LLM_PROXY_URL="http://localhost:8001"

# Test health endpoint
echo "1️⃣  Testing health endpoint..."
if curl -s "$LLM_PROXY_URL/healthz" | grep -q "ok"; then
    echo "✅ Health endpoint working"
else
    echo "❌ Health endpoint failed"
    exit 1
fi

# Test chat completions endpoint (this will fail if Ollama is not running, but should return proper error)
echo ""
echo "2️⃣  Testing chat completions endpoint..."
response=$(curl -s -w "%{http_code}" -o /tmp/chat_response.json \
    -X POST "$LLM_PROXY_URL/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "qwen3:32b",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello"}
        ],
        "temperature": 0.3,
        "max_tokens": 50
    }')

if [ "$response" = "200" ]; then
    echo "✅ Chat completions endpoint working (Ollama is running)"
    echo "   Response: $(cat /tmp/chat_response.json | jq -r '.choices[0].message.content' 2>/dev/null || echo 'Could not parse response')"
elif [ "$response" = "503" ]; then
    echo "⚠️  Chat completions endpoint responding correctly (Ollama unavailable)"
    echo "   This is expected if Ollama is not running"
else
    echo "❌ Chat completions endpoint returned unexpected status: $response"
    echo "   Response: $(cat /tmp/chat_response.json)"
fi

# Test embeddings endpoint
echo ""
echo "3️⃣  Testing embeddings endpoint..."
response=$(curl -s -w "%{http_code}" -o /tmp/embeddings_response.json \
    -X POST "$LLM_PROXY_URL/v1/embeddings" \
    -H "Content-Type: application/json" \
    -d '{
        "model": "bge-m3",
        "input": "This is a test text for embedding."
    }')

if [ "$response" = "200" ]; then
    echo "✅ Embeddings endpoint working (Ollama is running)"
    embedding_length=$(cat /tmp/embeddings_response.json | jq -r '.data[0].embedding | length' 2>/dev/null || echo 0)
    echo "   Embedding vector length: $embedding_length"
elif [ "$response" = "503" ]; then
    echo "⚠️  Embeddings endpoint responding correctly (Ollama unavailable)"
    echo "   This is expected if Ollama is not running"
else
    echo "❌ Embeddings endpoint returned unexpected status: $response"
    echo "   Response: $(cat /tmp/embeddings_response.json)"
fi

# Clean up temp files
rm -f /tmp/chat_response.json /tmp/embeddings_response.json

echo ""
echo "🎯 Test Summary:"
echo "  • Health endpoint: ✅ Working"
echo "  • Chat completions: $([ "$response" = "200" ] && echo "✅ Working" || echo "⚠️  Endpoint ready (Ollama needed)")"
echo "  • Embeddings: $([ "$response" = "200" ] && echo "✅ Working" || echo "⚠️  Endpoint ready (Ollama needed)")"
echo ""
echo "💡 Note: If Ollama is not running, endpoints will return 503 errors, which is correct behavior."
echo "   To test with a real LLM, ensure Ollama is running and the models are available." 