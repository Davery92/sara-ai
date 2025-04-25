"""
Auth helpers — *minimal* until we plug in a user DB.

• login()  → {access, refresh}
• verify() → payload | raises HTTPException
• refresh()→ new {access, refresh}
"""

import os, time
from datetime import timedelta
import jwt                                          # pip install "pyjwt[crypto]"
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

_ALG   = "HS256"
_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
_ACCESS_EXPIRE  = timedelta(minutes=15).total_seconds()
_REFRESH_EXPIRE = timedelta(days=7).total_seconds()

security = HTTPBearer(auto_error=False)

def _sign(data: dict, exp: float) -> str:
    payload = data | {"exp": time.time() + exp, "iat": time.time()}
    return jwt.encode(payload, _SECRET, algorithm=_ALG)

def login(username: str) -> dict:
    # ✅ replace with DB lookup later
    access  = _sign({"sub": username, "type": "access"},  _ACCESS_EXPIRE)
    refresh = _sign({"sub": username, "type": "refresh"}, _REFRESH_EXPIRE)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

def verify(creds: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    try:
        payload = jwt.decode(creds.credentials, _SECRET, algorithms=[_ALG])
        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("not an access token")
        return payload
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")

def refresh(refresh_token: str) -> dict:
    try:
        payload = jwt.decode(refresh_token, _SECRET, algorithms=[_ALG])
        if payload.get("type") != "refresh":
            raise jwt.InvalidTokenError("not a refresh token")
        return login(payload["sub"])
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        # Skip public paths:
        if request.url.path.startswith(("/healthz", "/auth")):
            return await call_next(request)

        # HTTPBearer parsed via `security` object we already defined
        try:
            payload = verify()
            request.state.user = payload["sub"]
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        return await call_next(request)

auth_middleware = AuthMiddleware