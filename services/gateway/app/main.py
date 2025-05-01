# services/gateway/app/main.py

from fastapi import FastAPI, Depends, Response
from fastapi.middleware import Middleware
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_models()
    yield
    # Shutdown (if needed)

app = FastAPI(
    redirect_slashes=False,
    middleware=[Middleware(auth_middleware)],
    lifespan=lifespan
)
app.include_router(metrics_router)

# ─── Public health check ─────────────────────────────────────────────────────
app.include_router(api_router)

# ─── Authentication endpoints ─────────────────────────────────────────────────
app.include_router(auth_router)

# ─── Protected "whoami" ───────────────────────────────────────────────────────
@app.get("/auth/me")
async def me(payload: dict = Depends(verify)):
    return {"user": payload["sub"], "iat": payload["iat"]}



# ─── LLM chat completions ────────────────────────────────────────────────────
app.include_router(chat_router)

# ─── Message queueing stub ────────────────────────────────────────────────────
app.include_router(messages_router)

app.include_router(ws_router)
app.include_router(chat_queue_router, prefix="/v1")
