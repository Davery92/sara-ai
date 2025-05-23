# Fix imports before anything else
from pathlib import Path
import sys

# Add both the app dir and project root to Python path
sys.path.insert(0, str(Path(__file__).parent.absolute()))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.absolute()))

from fastapi import FastAPI, Depends, Response
from fastapi import HTTPException, Request
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware  # Import CORS middleware
from contextlib import asynccontextmanager
import logging
import os

from .auth import auth_middleware, verify
from .routes.api import router as api_router
from .routes.auth import router as auth_router
from .routes.messages import router as messages_router
from .chat import router as chat_router  # Add chat router
from .db.session import init_models
from .ws import router as ws_router
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
from .metrics import router as metrics_router
from .routes.search import router as search_router
from .routes.memory import router as memory_router
# Use relative imports for local routes instead of absolute app imports
from .routes import api, auth, memory, search, messages, persona
# Import NATS client from the singleton module
from .utils.nats_singleton import nats_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger("gateway")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    log.info("Starting gateway application")
    await init_models()
    
    # Initialize NATS connection with retry
    try:
        log.info(f"Connecting to NATS server at {nats_client.url}")
        await nats_client.start(max_retries=10, delay=2.0)
        log.info("Successfully connected to NATS")
    except Exception as e:
        log.error(f"Failed to connect to NATS: {e}")
        log.warning("Starting without NATS connection - chat functionality will be limited")
    
    yield
    
    # Shutdown
    log.info("Shutting down gateway application")
    try:
        if hasattr(nats_client, 'nc') and nats_client.nc.is_connected:
            log.info("Draining NATS connection")
            await nats_client.nc.drain()
    except Exception as e:
        log.error(f"Error when closing NATS connection: {e}")

app = FastAPI(
    redirect_slashes=False,
    middleware=[Middleware(auth_middleware)],
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.include_router(metrics_router)

# ─── Public health check ─────────────────────────────────────────────────────
app.include_router(api.router)

# ─── Authentication endpoints ─────────────────────────────────────────────────
app.include_router(auth.router)

# ─── Protected "whoami" ───────────────────────────────────────────────────────
@app.get("/auth/me")
async def me(payload: dict = Depends(verify)):
    return {"user": payload["sub"], "iat": payload["iat"]}

# Add a route to check NATS connection status
@app.get("/api/nats/status")
async def nats_status():
    if not hasattr(nats_client, 'nc') or not nats_client.nc.is_connected:
        raise HTTPException(status_code=503, detail="NATS connection is down")
    return {"status": "connected", "url": nats_client.url}

# ─── LLM chat completions ────────────────────────────────────────────────────
app.include_router(chat_router)

# ─── Message queueing stub ────────────────────────────────────────────────────
app.include_router(messages.router)

app.include_router(ws_router)
# Import the chat_queue router after initializing app to avoid circular imports
from .routes.chat_queue import router as chat_queue_router
app.include_router(chat_queue_router, prefix="/v1")
app.include_router(search.router)
app.include_router(memory.router)
app.include_router(persona.router)  # Add our new persona router
