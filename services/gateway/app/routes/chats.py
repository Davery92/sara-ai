from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime
from ..deps.auth import get_jwt_token, get_current_user
from ..db.session import get_session
from sqlalchemy.ext.asyncio import AsyncSession
import logging

# Set up logging
log = logging.getLogger("gateway.chats")

# Create router
router = APIRouter(tags=["chats"])

# Models for chat operations
class ChatBase(BaseModel):
    title: Optional[str] = "New Chat"
    visibility: str = "private"  # private or public

    class Config:
        alias_generator = to_camel
        populate_by_name = True
        from_attributes = True

class ChatCreate(ChatBase):
    id: Optional[str] = None

class ChatUpdate(ChatBase):
    pass

class ChatResponse(ChatBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class MessageBase(BaseModel):
    role: str  # user, assistant, system
    content: str
    parts: Optional[List[dict]] = None

    class Config:
        alias_generator = to_camel
        populate_by_name = True
        from_attributes = True

class MessageCreate(MessageBase):
    pass

class MessageResponse(MessageBase):
    id: str
    chat_id: str = Field(..., alias="chatId")
    created_at: datetime

# Chat routes
@router.post("/api/chats", response_model=ChatResponse, status_code=201)
async def create_chat(
    chat: ChatCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Create a new chat conversation"""
    # Log the request
    log.info(f"Creating new chat for user {current_user['sub']}")
    
    # You can implement the actual database operation here
    # For now, we'll return a mock response
    chat_id = chat.id if chat.id else str(uuid4())
    now = datetime.utcnow()
    
    # In a real implementation, you would save this to the database
    return ChatResponse(
        id=chat_id,
        title=chat.title,
        visibility=chat.visibility,
        created_at=now,
        updated_at=now
    )

@router.get("/api/chats", response_model=List[ChatResponse])
async def get_chats(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Get all chats for the current user"""
    # In a real implementation, you would query the database
    # For now, we'll return a mock response
    now = datetime.utcnow()
    return [
        ChatResponse(
            id=str(uuid4()),
            title="Mock Chat",
            visibility="private",
            created_at=now
        )
    ]

@router.get("/api/chats/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Get a specific chat by ID"""
    # In a real implementation, you would query the database
    # For now, we'll return a mock response
    return ChatResponse(
        id=chat_id,
        title="Chat Details",
        visibility="private",
        created_at=datetime.utcnow()
    )

@router.put("/api/chats/{chat_id}", response_model=ChatResponse)
async def update_chat(
    chat: ChatUpdate,
    chat_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Update a chat"""
    # In a real implementation, you would update the database
    return ChatResponse(
        id=chat_id,
        title=chat.title,
        visibility=chat.visibility,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

@router.delete("/api/chats/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Delete a chat"""
    # In a real implementation, you would delete from the database
    return None

# Chat message routes
@router.post("/api/chats/{chat_id}/messages", response_model=MessageResponse, status_code=201)
async def create_message(
    message: MessageCreate,
    chat_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Add a message to a chat"""
    # In a real implementation, you would add to the database
    return MessageResponse(
        id=str(uuid4()),
        chat_id=chat_id,
        role=message.role,
        content=message.content,
        parts=message.parts,
        created_at=datetime.utcnow()
    )

@router.get("/api/chats/{chat_id}/messages", response_model=List[MessageResponse])
async def get_chat_messages(
    chat_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Get all messages for a specific chat"""
    # In a real implementation, you would query the database
    now = datetime.utcnow()
    return [
        MessageResponse(
            id=str(uuid4()),
            chat_id=chat_id,
            role="user",
            content="Hello, assistant!",
            parts=[{"type": "text", "text": "Hello, assistant!"}],
            created_at=now
        ),
        MessageResponse(
            id=str(uuid4()),
            chat_id=chat_id,
            role="assistant",
            content="Hello! How can I help you today?",
            parts=[{"type": "text", "text": "Hello! How can I help you today?"}],
            created_at=now
        )
    ] 