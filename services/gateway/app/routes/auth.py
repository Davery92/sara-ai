# services/gateway/app/routes/auth.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import jwt
from ..auth import _SECRET, _ALG, login as issue_tokens
from ..redis_client import get_redis  # Correct import
from fastapi import status


router = APIRouter(prefix="/auth", tags=["auth"])

class LoginIn(BaseModel):
    username: str

class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshIn(BaseModel):
    refresh_token: str

class SignupRequest(BaseModel):
    username: str
    password: str

@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(req: SignupRequest):
    # TODO: persist the new user & hash the password
    # For now we just return a token so you can test search:
    tokens = issue_tokens(req.username)
    return tokens

@router.post("/auth/login") 
@router.post("/login", response_model=TokenOut)
async def login_route(payload: LoginIn):
    return issue_tokens(payload.username)

@router.post("/auth/refresh") 
@router.post("/refresh", response_model=TokenOut)
async def refresh_route(payload: RefreshIn):
    # In-memory blacklist for testing (since Redis might not be available)
    if not hasattr(refresh_route, "_blacklist"):
        refresh_route._blacklist = set()
        
    try:
        token_data = jwt.decode(payload.refresh_token, _SECRET, algorithms=[_ALG])
        if token_data.get("type") != "refresh":
            raise jwt.InvalidTokenError("Not a refresh token")
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=str(e))

    old_jti = token_data["jti"]

    # Check in-memory blacklist first
    if old_jti in refresh_route._blacklist:
        raise HTTPException(status_code=401, detail="Token already used (blacklisted)")

    try:
        redis = await get_redis()
        if redis:
            already_blacklisted = await redis.get(f"blacklist:{old_jti}")
            if already_blacklisted:
                raise HTTPException(status_code=401, detail="Token already used (blacklisted)")
            # Blacklist the token with expiration
            await redis.set(f"blacklist:{old_jti}", "1", ex=int(token_data["exp"] - token_data["iat"]))
        else:
            # If Redis is not available, use in-memory blacklist
            refresh_route._blacklist.add(old_jti)
    except Exception as e:
        # If Redis fails, use in-memory blacklist
        refresh_route._blacklist.add(old_jti)
        import logging
        logging.warning(f"Redis error (falling back to in-memory blacklist): {e}")

    return issue_tokens(token_data["sub"])