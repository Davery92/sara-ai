# services/gateway/app/routes/auth.py

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import os

from ..auth import _sign, _ALG, _SECRET, _ACCESS_EXPIRE, _REFRESH_EXPIRE, login
from ..redis_client import get_redis

router = APIRouter(prefix="/auth")
bearer = HTTPBearer(auto_error=True)

@router.post("/login")
async def login_endpoint(username: str = Body(..., embed=True)):
    """
    Stub login – returns access_token & refresh_token
    """
    return login(username)


@router.post("/refresh")
async def refresh_endpoint(
    refresh_token: str = Body(..., embed=True)
):
    """
    Consume a refresh_token, blacklist its JTI, and issue new tokens.
    """
    try:
        payload = jwt.decode(refresh_token, _SECRET, algorithms=[_ALG])
        if payload.get("type") != "refresh":
            raise jwt.InvalidTokenError("Not a refresh token")
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

    # blacklist the old refresh token
    redis = await get_redis()
    await redis.set(f"blacklist:{payload['jti']}", "1", ex=int(_REFRESH_EXPIRE))

    # issue fresh tokens
    new_access, _  = _sign({"sub": payload["sub"], "type": "access"},  _ACCESS_EXPIRE)
    new_refresh, _ = _sign({"sub": payload["sub"], "type": "refresh"}, _REFRESH_EXPIRE)
    return {
        "access_token":  new_access,
        "refresh_token": new_refresh,
        "token_type":    "bearer"
    }


@router.post("/logout")
async def logout_endpoint(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    refresh_token: str = Body(..., embed=True),
):
    """
    Blacklist both the presented access_token and the given refresh_token.
    """
    # blacklist current access token
    try:
        data = jwt.decode(credentials.credentials, _SECRET, algorithms=[_ALG])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid access token")

    redis = await get_redis()
    await redis.set(f"blacklist:{data['jti']}", "1", ex=int(_ACCESS_EXPIRE))

    # blacklist the provided refresh token
    try:
        rdata = jwt.decode(refresh_token, _SECRET, algorithms=[_ALG])
        await redis.set(f"blacklist:{rdata['jti']}", "1", ex=int(_REFRESH_EXPIRE))
    except jwt.PyJWTError:
        pass

    return {"detail": "Logged out"}
