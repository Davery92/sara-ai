from fastapi import FastAPI, Depends, Request
from fastapi.middleware import Middleware
from .auth import (
    AuthMiddleware,       # <— middleware class
    login, verify, refresh,
)

# ─── FastAPI app with global auth middleware ─────────────────────────
middleware = [Middleware(AuthMiddleware)]
app = FastAPI(middleware=middleware)

# ─── Auth endpoints (public) ─────────────────────────────────────────
@app.post("/auth/login")
def _login(username: str = "demo"):          # TODO: replace stub auth
    return login(username)

@app.post("/auth/refresh")
def _refresh(token: str):
    return refresh(token)

# ─── Example protected endpoint ──────────────────────────────────────
@app.get("/auth/me")
def _me(payload: dict = Depends(verify)):
    return {"user": payload["sub"], "iat": payload["iat"]}

# ─── Health + chat routers (already created) ─────────────────────────
from .api import router as api_router
from .chat import router as chat_router
app.include_router(api_router)
app.include_router(chat_router)
