# services/gateway/app/routes/auth.py

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_
from ..auth import _SECRET, _ALG, login as issue_tokens, verify as verify_token # FIXED: Relative import
from ..redis_client import get_redis # FIXED: Relative import
from fastapi import status
from ..db.session import get_session # FIXED: Relative import
from ..db.models import User # FIXED: Relative import
from ..utils.password import hash_password, verify_password # FIXED: Relative import
import logging
from uuid import UUID # ADDED: Import UUID

# Set up logger
log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginIn(BaseModel):
    username: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshIn(BaseModel):
    refresh_token: str

class SignupRequest(BaseModel):
    username: str
    password: str

class UserOut(BaseModel):
    username: str
    id: str

@router.post("/signup", status_code=status.HTTP_201_CREATED, response_model=TokenOut)
async def signup(req: SignupRequest, session: AsyncSession = Depends(get_session)):
    # Check if user already exists
    result = await session.execute(select(User).where(User.username == req.username))
    existing_user = result.scalars().first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists"
        )
    
    # Hash the password and create a new user
    hashed_password = hash_password(req.password)
    new_user = User(username=req.username, password_hash=hashed_password)
    
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user) # ADDED: Refresh to get the generated UUID
    
    # Issue tokens for the new user, using its generated UUID
    tokens = issue_tokens(new_user.id) # FIXED: Pass new_user.id (UUID)
    return tokens

@router.post("/login", response_model=TokenOut)
async def login_route(payload: LoginIn, session: AsyncSession = Depends(get_session)):
    # Find user by username
    result = await session.execute(select(User).where(User.username == payload.username))
    user = result.scalars().first()
    
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    return issue_tokens(user.id) # FIXED: Pass user.id (UUID)

@router.get("/me")
async def get_current_user(request: Request):
    """
    Get the current authenticated user's profile
    
    This is a simplified endpoint that manually extracts and verifies the token
    """
    try:
        auth_header = request.headers.get('authorization')
        if not auth_header:
            log.warning("No authorization header for /auth/me")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing authorization header"
            )
        
        # Extract token
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            log.warning(f"Invalid auth header format: {auth_header[:20]}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid authorization format"
            )
        
        token = parts[1]
        
        # Decode token manually
        try:
            log.info(f"Decoding token for /auth/me: {token[:20]}...")
            payload = jwt.decode(token, _SECRET, algorithms=[_ALG])
            
            # Check token type
            if payload.get('type') != 'access':
                log.warning("Token is not an access token")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not an access token"
                )
                
            user_id_str = payload.get('sub') # This will now be the UUID string
            if not user_id_str:
                log.warning("Token missing 'sub' claim")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: missing user identifier"
                )
            
            # Optionally, look up username from user_id if UI needs username
            # For now, just pass the user_id (UUID string) as 'user'
            log.info(f"Token verified successfully for user ID {user_id_str}")
            return {
                "user": user_id_str, # Frontend expects "user" to be the identifier
                "iat": payload.get("iat")
            }
            
        except jwt.ExpiredSignatureError:
            log.warning("Token expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired"
            )
        except jwt.PyJWTError as e:
            log.warning(f"Invalid token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Unexpected error in /auth/me: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process authentication"
        )

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

    # Pass the user ID (from the refresh token) to issue_tokens
    user_id_from_token = token_data["sub"] # This will be the UUID string
    return issue_tokens(UUID(user_id_from_token)) # FIXED: Convert back to UUID before passing
