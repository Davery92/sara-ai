from typing import Dict, List, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from services.common.persona_service import get_persona_service, PersonaService
from app.redis_client import get_redis
from app.auth import get_user_id

router = APIRouter(prefix="/v1/persona", tags=["persona"])

# Redis key for storing user persona preferences
USER_PERSONA_KEY = "user:persona:{user_id}"

@router.get("/config", response_model=Dict[str, Any])
async def get_persona_config(
    persona_name: Optional[str] = None,
    user_id: Optional[str] = Depends(get_user_id),
    persona_service: PersonaService = Depends(get_persona_service),
    redis_client = Depends(get_redis)
):
    """
    Get persona configuration. If persona_name is provided, returns that persona.
    If not, looks up the user's preferred persona or returns the default.
    """
    # If no specific persona requested, check for user preference
    if not persona_name and user_id:
        redis_key = USER_PERSONA_KEY.format(user_id=user_id)
        persona_name = await redis_client.get(redis_key)
        
    # If still no persona, use default
    if not persona_name:
        persona_name = persona_service.get_default_persona()
    
    try:
        return persona_service.get_persona_config(persona_name)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona '{persona_name}' not found"
        )

@router.get("/list", response_model=List[str])
async def list_personas(
    persona_service: PersonaService = Depends(get_persona_service)
):
    """List all available personas."""
    return persona_service.get_available_personas()

@router.patch("", response_model=Dict[str, str])
async def set_user_persona(
    persona: Dict[str, str],
    user_id: str = Depends(get_user_id),
    persona_service: PersonaService = Depends(get_persona_service),
    redis_client = Depends(get_redis)
):
    """Set user's preferred persona."""
    persona_name = persona.get("persona")
    if not persona_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'persona' field"
        )
    
    # Validate that the persona exists
    if persona_name not in persona_service.get_available_personas():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Persona '{persona_name}' not found"
        )
    
    # Store user preference in Redis
    redis_key = USER_PERSONA_KEY.format(user_id=user_id)
    await redis_client.set(redis_key, persona_name)
    
    return {"status": "success", "persona": persona_name} 