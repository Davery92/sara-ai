# Memory Worker Fixes

This document outlines the fixes applied to resolve the memory worker issues where LLM calls were failing and Redis keys were not being cleaned up properly.

## Root Causes Identified

1. **Missing Endpoints on llm_proxy**: The llm_proxy service only had WebSocket endpoints but the memory worker needed HTTP endpoints for:
   - `POST /v1/chat/completions` (for generating summaries)
   - `POST /v1/embeddings` (for generating embeddings)

2. **Missing Database Configuration**: The memory worker was missing PostgreSQL environment variables needed to save summaries to the database.

3. **Missing PostgreSQL Dependencies**: The memory worker container was missing the `psycopg2-binary` and `asyncpg` packages required to connect to PostgreSQL.

4. **Redis Data Not Cleared on Failure**: When LLM calls failed, the Redis keys `user:{user_id}:messages` remained until TTL expiry, causing reprocessing loops.

## Solutions Implemented

### 1. Added Missing HTTP Endpoints to llm_proxy

**File**: `services/llm_proxy/app/main.py`

- Added `POST /v1/chat/completions` endpoint that forwards requests to Ollama
- Added `POST /v1/embeddings` endpoint that forwards requests to Ollama  
- Both endpoints include proper error handling and timeout configuration
- Updated imports to include `Request` and `HTTPException`
- Consolidated Ollama URL configuration using `OLLAMA_URL_INTERNAL`

Key features:
- Non-streaming chat completions (sets `stream=False` by default)
- Proper error propagation from Ollama to the client
- Configurable timeouts (60s for completions, 30s for embeddings)
- Comprehensive logging

### 2. Updated Memory Worker Configuration

**File**: `workflows/memory_worker/activities.py`

- Changed `LLM_BASE_URL` to use `LLM_PROXY_URL` environment variable
- Default URL now points to `http://llm_proxy:8000` instead of direct Ollama access

**File**: `compose/core.yml`

- Updated memory worker environment to use `LLM_PROXY_URL: "http://llm_proxy:8000"`
- Added missing PostgreSQL environment variables for database access
- Added `env_file` reference to load environment variables from `.env`
- Updated service dependencies to ensure proper startup order
- Ensures the memory worker calls the proxy instead of Ollama directly

### 3. Added Missing PostgreSQL Dependencies

**File**: `workflows/memory_worker/Dockerfile`

- Added `psycopg2-binary>=2.9.9` for PostgreSQL connectivity
- Added `asyncpg>=0.29` for async PostgreSQL operations
- Added `SQLAlchemy>=2.0` for ORM functionality
- Ensures the memory worker can connect to and save data to PostgreSQL

### 4. Improved Redis Key Deletion Logic

**File**: `workflows/memory_worker/activities.py`

Enhanced the `process_rooms` function with:
- Added `processed_successfully` flag to track processing state
- Moved Redis key deletion to a `finally` block
- Always delete Redis keys if chunks were fetched, even on LLM failures
- Different log messages for successful vs failed processing cleanup

This prevents reprocessing loops when LLM services are temporarily unavailable.

## Testing

**File**: `services/llm_proxy/tests/test_http_endpoints.py`

Created comprehensive tests for the new endpoints:
- Health check endpoint verification
- Successful chat completions and embeddings requests
- Error handling for Ollama failures
- Verification that `stream=False` is set for chat completions

## Benefits

1. **Reliability**: Memory worker can now successfully call LLM services through the proxy
2. **Error Recovery**: Redis keys are cleaned up even when LLM calls fail, preventing infinite reprocessing
3. **Consistency**: All LLM calls go through the same proxy service
4. **Monitoring**: Better logging and error handling throughout the pipeline
5. **Testability**: New endpoints are properly tested

## Configuration

The memory worker now uses these environment variables:
- `LLM_PROXY_URL`: URL of the llm_proxy service (default: `http://llm_proxy:8000`)
- `EMBEDDING_MODEL`: Model for embeddings (default: `bge-m3`)
- `SUMMARY_MODEL`: Model for summaries (default: `qwen3:32b`)
- `API_TIMEOUT`: Timeout for API calls (default: `30.0` seconds)

## Deployment

To apply these fixes:

1. Rebuild the llm_proxy service: `docker-compose build llm_proxy`
2. Rebuild the memory worker: `docker-compose build memory_worker`
3. Restart the services: `docker-compose up -d llm_proxy memory_worker`

The changes are backward compatible and don't require database migrations. 