# services/gateway/app/main.py
# Fix imports before anything else
from pathlib import Path
import sys

# Add both the app dir and project root to Python path
sys.path.insert(0, str(Path(__file__).parent.absolute()))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.absolute()))

from fastapi import FastAPI, Depends, Response
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware  # Import CORS middleware
from contextlib import asynccontextmanager

from .auth import auth_middleware, verify
from .routes.api import router as api_router
from .routes.auth import router as auth_router
from .routes.messages import router as messages_router
from .chat import router as chat_router  # Add chat router
from .db.session import init_models
from .ws import router as ws_router
from .routes.chat_queue import router as chat_queue_router
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
from .metrics import router as metrics_router
from .routes.search import router as search_router
from .routes.memory import router as memory_router
# Use relative imports for local routes instead of absolute app imports
from .routes import api, auth, chat_queue, memory, search, messages, persona
from .nats_client import GatewayNATS

nats_client = GatewayNATS("nats://nats:4222")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_models()
    yield
    await nats_client.nc.drain()

    # Shutdown (if needed)

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



# ─── LLM chat completions ────────────────────────────────────────────────────
app.include_router(chat_router)

# ─── Message queueing stub ────────────────────────────────────────────────────
app.include_router(messages.router)

app.include_router(ws_router)
app.include_router(chat_queue.router, prefix="/v1")
app.include_router(search.router)
app.include_router(memory.router)
app.include_router(persona.router)  # Add our new persona router
