# services/gateway/app/auth.py

import os, time, logging
from datetime import timedelta
from uuid import uuid4
from uuid import UUID
import uuid

import jwt  # pip install "pyjwt[crypto]"
from fastapi import HTTPException, status, Depends, Header
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
            
        # Path normalization: Strip /v1 prefix if present for path checking
        path = request.url.path
        
        # Fix double slashes in path - normalize the path
        while '//' in path:
            path = path.replace('//', '/')
            
        normalized_path = path[3:] if path.startswith("/v1") else path
        
        # Always allow these paths without authentication
        if normalized_path.startswith((
            "/healthz", "/metrics",
            "/signup",  "/auth/signup",
            "/login",   "/auth/login",
            "/refresh", "/auth/refresh",
            # Note: /auth/me is intentionally NOT included here as it requires auth
            "/search",
        )):
            return await call_next(request)
        
        # Log the authorization header for debugging
        auth_header = request.headers.get("authorization", "")
        log.info(f"Request to {path} with auth: {auth_header[:20] + '...' if auth_header else 'none'}")
        
        try:
            creds = await security(request)
            payload = await verify(creds)
            request.state.user = payload["sub"]
        except HTTPException as exc:
            log.warning(f"Auth failed for {path}: {exc.detail}")
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await call_next(request)


auth_middleware = AuthMiddleware

async def get_current_user_id(authorization: str = Header(None)) -> uuid.UUID:
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated, Authorization header is missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    parts = authorization.split()

    if parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif len(parts) == 1:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif len(parts) > 2:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALG])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, # 403 as token is valid but sub missing
                detail="Invalid token: 'sub' (subject/user ID) claim missing"
            )
        
        # Ensure the user_id is a valid UUID
        try:
            return uuid.UUID(user_id_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Invalid token: 'sub' claim '{user_id_str}' is not a valid UUID"
            )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer error=\"invalid_token\", error_description=\"The token has expired\""},
        )
    except jwt.InvalidTokenError as e: # Catches various other JWT errors (invalid signature, malformed, etc.)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer error=\"invalid_token\""},
        )
    except Exception as e: # Catch-all for unexpected errors during parsing
        # Log this error server-side for investigation
        # log.error(f"Unexpected error during token decoding: {str(e)}") 
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not process authentication token due to an internal error"
        )
