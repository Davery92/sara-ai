# services/gateway/app/main.py

from fastapi import FastAPI, Depends, Request
from fastapi.middleware import Middleware
from fastapi.responses import JSONResponse
from .routes.messages import router as messages_router

from .auth import auth_middleware, verify
from .routes.auth import router as auth_router
from .api import router as api_router
from .chat import router as chat_router
from .db.session import init_models


app = FastAPI(redirect_slashes=False, middleware=[Middleware(auth_middleware)])

# ─── Auth routes (login, refresh, logout) ───────────────────────────────
app.include_router(auth_router)

@app.on_event("startup")
async def on_startup():
    await init_models()

# ─── Protected “me” example ─────────────────────────────────────────────
@app.get("/auth/me")
def me(payload: dict = Depends(verify)):
    return {"user": payload["sub"], "iat": payload["iat"]}

# ─── Other feature routers ────────────────────────────────────────────────
app.include_router(api_router)
app.include_router(chat_router)
app.include_router(messages_router)
