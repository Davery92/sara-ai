#!/bin/bash

# Memory Worker Fixes Deployment Script
# This script deploys the fixes for the memory worker LLM proxy issues

set -e  # Exit on any error

echo "🚀 Deploying Memory Worker Fixes..."
echo "=================================="

# Check if we're in the right directory
if [ ! -f "compose/core.yml" ]; then
    echo "❌ Error: Please run this script from the sara-ai project root directory"
    exit 1
fi

# Build the updated services
echo "📦 Building updated services..."
docker-compose -f compose/core.yml build llm_proxy memory_worker

# Stop the existing services
echo "🛑 Stopping existing services..."
docker-compose -f compose/core.yml stop llm_proxy memory_worker

# Start the updated services
echo "▶️  Starting updated services..."
docker-compose -f compose/core.yml up -d llm_proxy memory_worker

# Wait a moment for services to start
echo "⏳ Waiting for services to start..."
sleep 5

# Check service health
echo "🔍 Checking service health..."

# Check llm_proxy health
if curl -s http://localhost:8001/healthz | grep -q "ok"; then
    echo "✅ llm_proxy service is healthy"
else
    echo "❌ llm_proxy service health check failed"
fi

# Check if memory_worker container is running
if docker-compose -f compose/core.yml ps memory_worker | grep -q "Up"; then
    echo "✅ memory_worker service is running"
else
    echo "❌ memory_worker service is not running"
fi

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📋 Summary of changes:"
echo "  • Added HTTP endpoints to llm_proxy:"
echo "    - POST /v1/chat/completions (for summaries)"
echo "    - POST /v1/embeddings (for embeddings)"
echo "  • Updated memory worker to use llm_proxy instead of direct Ollama"
echo "  • Added missing PostgreSQL environment variables to memory worker"
echo "  • Added missing PostgreSQL dependencies (psycopg2-binary, asyncpg)"
echo "  • Improved Redis key cleanup to prevent reprocessing loops"
echo ""
echo "🔗 Service URLs:"
echo "  • llm_proxy: http://localhost:8001"
echo "  • llm_proxy health: http://localhost:8001/healthz"
echo ""
echo "📊 To monitor the services:"
echo "  docker-compose -f compose/core.yml logs -f llm_proxy memory_worker"
echo ""
echo "📖 For more details, see: MEMORY_WORKER_FIXES.md" 