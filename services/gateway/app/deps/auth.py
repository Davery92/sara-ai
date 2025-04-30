from fastapi import Header, HTTPException, status

def get_jwt_token(authorization: str = Header(None)) -> str:
    """
    Extracts `Bearer <jwt>` from the incoming HTTP header.
    Raises 401 if the header is missing or malformed.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
        )
    return authorization[7:].strip()
