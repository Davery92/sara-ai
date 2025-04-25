from fastapi import Request
from typing import Callable
from starlette.responses import Response

async def auth_middleware(request: Request, call_next: Callable) -> Response:
    """
    Stub JWT auth:
    • Reads the Authorization header (we’ll validate it later)
    • Sets request.state.user_id = None for now
    """
    # raw_token = request.headers.get("Authorization", "")
    request.state.user_id = None
    return await call_next(request)
