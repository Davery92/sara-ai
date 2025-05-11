# services/gateway/app/auth.py

import os, time, logging
from datetime import timedelta
from uuid import uuid4

import jwt  # pip install "pyjwt[crypto]"
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse

from .redis_client import get_redis

# Set up logging
log = logging.getLogger(__name__)

# ── JWT settings ────────────────────────────────────────────────
_ALG            = "HS256"
_SECRET         = os.getenv("JWT_SECRET", "dev-secret-change-me")
# Increase token expiration times for development
_ACCESS_EXPIRE  = timedelta(days=7).total_seconds()  # Increased from 15 minutes to 7 days for development
_REFRESH_EXPIRE = timedelta(days=30).total_seconds() # Increased from 7 days to 30 days

security = HTTPBearer(auto_error=False)


def _sign(payload: dict, exp_seconds: float) -> tuple[str, str]:
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
    """
    Returns a dict with access_token, refresh_token, token_type.
    
    Note: Password validation is done in the route handler, not here.
    This function simply issues tokens for the given username.
    """
    log.info(f"Generating tokens for user: {username}")
    access_token, access_jti   = _sign({"sub": username, "type": "access"},  _ACCESS_EXPIRE)
    refresh_token, refresh_jti = _sign({"sub": username, "type": "refresh"}, _REFRESH_EXPIRE)
    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "token_type":    "bearer",
    }


async def verify(
    creds: HTTPAuthorizationCredentials | None = Depends(security)
) -> dict:
    """
    Dependency that validates an access token and enforces blacklist.
    """
    if not creds:
        log.warning("No credentials provided for verification")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing token")
    try:
        log.info(f"Verifying token: {creds.credentials[:20]}...")
        payload = jwt.decode(creds.credentials, _SECRET, algorithms=[_ALG])
        if payload.get("type") != "access":
            log.warning(f"Invalid token type: {payload.get('type')}")
            raise jwt.InvalidTokenError("Not an access token")
        # check blacklist
        jti = payload["jti"]
        try:
            redis = await get_redis()
            if redis and await redis.get(f"blacklist:{jti}"):
                log.warning(f"Token {jti} is blacklisted")
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")
        except Exception as e:
            log.warning(f"Redis error checking blacklist: {e}")
            # Redis down → skip
            pass
        
        log.info(f"Token verified successfully for user {payload.get('sub')}")
        return payload
    except jwt.ExpiredSignatureError:
        log.warning("Token expired")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except jwt.PyJWTError as e:
        log.warning(f"Invalid token: {e}")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {e}")


async def get_user_id(payload: dict = Depends(verify)) -> str:
    """
    Dependency that extracts the user ID from the JWT token.
    
    Returns the user ID ('sub' field) from the JWT payload.
    If no valid token is present, returns None.
    """
    return payload.get("sub")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Allow OPTIONS requests for CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)
            
        if request.url.path.startswith((
            "/healthz", "/metrics",
            "/signup",  "/auth/signup",
            "/login",   "/auth/login",
            "/refresh", "/auth/refresh",   # ← add these two
            "/v1/search",
        )):
            return await call_next(request)
        
        # Log the authorization header for debugging
        auth_header = request.headers.get("authorization", "")
        log.info(f"Request to {request.url.path} with auth: {auth_header[:20] + '...' if auth_header else 'none'}")
        
        try:
            creds = await security(request)
            payload = await verify(creds)
            request.state.user = payload["sub"]
        except HTTPException as exc:
            log.warning(f"Auth failed for {request.url.path}: {exc.detail}")
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await call_next(request)


auth_middleware = AuthMiddleware
