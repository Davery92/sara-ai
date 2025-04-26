import os, time
from datetime import timedelta
from uuid import uuid4

import jwt                                          # pip install "pyjwt[crypto]"
from fastapi import HTTPException, status, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .redis_client import get_redis

# ── JWT settings ───────────────────────────────
_ALG            = "HS256"
_SECRET         = os.getenv("JWT_SECRET", "dev-secret-change-me")
_ACCESS_EXPIRE  = timedelta(minutes=15).total_seconds()
_REFRESH_EXPIRE = timedelta(days=7).total_seconds()

security = HTTPBearer(auto_error=False)



def _sign(payload: dict, exp_seconds: float) -> tuple[str,str]:
    jti = str(uuid4())
    data = {
        **payload,
        "jti": jti,
        "iat": time.time(),
        "exp": time.time() + exp_seconds,
    }
    token = jwt.encode(data, _SECRET, algorithm=_ALG)
    return token, jti


def login(username: str) -> dict:
    # replace with DB lookup later
    access_token, access_jti   = _sign({"sub": username, "type": "access"},  _ACCESS_EXPIRE)
    refresh_token, refresh_jti = _sign({"sub": username, "type": "refresh"}, _REFRESH_EXPIRE)
    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "token_type":    "bearer",
        # optionally return JTIs for testing:
        # "access_jti": access_jti,
        # "refresh_jti": refresh_jti,
    }


async def verify(creds: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:

    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    try:
        payload = jwt.decode(creds.credentials, _SECRET, algorithms=[_ALG])
        if payload.get("type") != "access":
            raise jwt.InvalidTokenError("Not an access token")
        # check blacklist
        jti = payload["jti"]
        redis =  await get_redis()
        if await redis.get(f"blacklist:{jti}"):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")
        return payload
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        # skip auth on public paths
        if request.url.path.startswith(("/healthz", "/auth")):
            return await call_next(request)

        try:
            # extract bearer credentials
            creds = await security(request)
            # verify token and check blacklist
            payload = await verify(creds)
            # store user on request.state for downstream handlers
            request.state.user = payload["sub"]
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

        # all good → continue to next handler
        return await call_next(request)

auth_middleware = AuthMiddleware
