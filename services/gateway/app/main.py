# services/gateway/app/main.py
# Fix imports before anything else
from pathlib import Path
import sys
import os
import httpx
# Add both the app dir and project root to Python path
sys.path.insert(0, str(Path(__file__).parent.absolute()))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.absolute()))

from fastapi import FastAPI, Depends, Response
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware  # Import CORS middleware
from contextlib import asynccontextmanager
import logging  # Add logging

from .auth import auth_middleware, verify
from .routes.api import router as api_router
from .routes.auth import router as auth_router
from .routes.messages import router as messages_router
from .chat import router as chat_router  # Add chat router
from .db.session import init_models
from .ws import router as ws_router
# from .routes.chat_queue import router as chat_queue_router # COMMENT OUT
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
from .metrics import router as metrics_router
from .routes.search import router as search_router
from .routes.memory import router as memory_router
# Use relative imports for local routes instead of absolute app imports
from .routes import api, auth, memory, search, messages, persona, artifacts, files, chats # REMOVE chat_queue
from .nats_client import GatewayNATS

# Configure logging - SET TO DEBUG
logging.basicConfig(
    level=logging.DEBUG, # CHANGE THIS TO DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger("gateway.main")  # Logger for this module

nats_client = GatewayNATS(os.getenv("NATS_URL", "nats://nats:4222"))  # Use env var for consistency


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    log.info("Application startup...")
    await init_models()
    log.info("Database models initialized.")

    try:
        log.info(f"Attempting to connect to NATS server at {nats_client.url}...")
        await nats_client.start(max_retries=10, delay=2.0)
        log.info("Successfully connected to NATS and started client.")
    except Exception as e:
        log.error(f"Failed to connect to NATS during startup: {e}")
        # Continue without raising to allow app to start

    yield  # Application runs here

    # Shutdown
    log.info("Application shutdown...")
    if nats_client.nc and getattr(nats_client.nc, 'is_connected', False):
        try:
            log.info("Draining NATS connection...")
            await nats_client.nc.drain()
            log.info("NATS connection drained.")
        except Exception as e:
            log.error(f"Error during NATS drain: {e}")
    elif nats_client.nc and not getattr(nats_client.nc, 'is_closed', True):
        try:
            log.info("NATS client was not connected, attempting to close.")
            await nats_client.nc.close()
            log.info("NATS connection closed.")
        except Exception as e:
            log.error(f"Error closing NATS connection during shutdown: {e}")
    else:
        log.info("NATS client was not connected or already closed. Skipping drain/close.")
    log.info("Application shutdown complete.")

app = FastAPI(
    redirect_slashes=False,
    middleware=[Middleware(auth_middleware)],
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (you might want to restrict this in production)
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


# ─── Chat management endpoints ───────────────────────────────────────────────
app.include_router(chats.router)

# ─── LLM chat completions ────────────────────────────────────────────────────
app.include_router(chat_router)

# ─── Message queueing stub ────────────────────────────────────────────────────
app.include_router(messages.router)

app.include_router(ws_router)
# app.include_router(chat_queue.router, prefix="/v1") # COMMENT OUT
app.include_router(search.router)
app.include_router(memory.router)
app.include_router(persona.router)  # Add our new persona router
app.include_router(artifacts.router)  # Add artifacts router
app.include_router(files.router)  # Add files router for file uploads

@app.get("/health/all")
async def check_all_health():
    return {"ok": True}
    
    # Check LLM Proxy
    async def check_llm_proxy_health():
        llm_proxy_url = os.getenv("LLM_WS_URL", "ws://llm_proxy:8000")
        http_url = llm_proxy_url.replace('ws://', 'http://').replace('wss://', 'https://').split('/v1/')[0]
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{http_url}/healthz", timeout=2.0)
                if resp.status_code == 200:
                    return True
                return False
        except Exception:
            return False
    
    return {
        "gateway": True,
        "nats": await check_nats_health(),
        "llm_proxy": await check_llm_proxy_health()
    }
