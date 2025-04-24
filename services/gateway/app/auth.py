from fastapi import Request
from typing import Optional

async def auth_middleware(request: Request, call_next):
    """
    Stub JWT auth:
    • Reads the Authorization header (we’ll validate it later)
    • Sets request.state.user_id = None for now
    """
    # raw = request.headers.get("Authorization", "")
    # TODO: parse JWT and set user_id here
    request.state.user_id = None
    response = await call_next(request)
    return response
