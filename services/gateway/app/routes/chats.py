from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime
import json # Import json for serialization/deserialization

from ..deps.auth import get_jwt_token, get_current_user # FIXED: Corrected import path for deps
from ..db.session import get_session
from sqlalchemy.ext.asyncio import AsyncSession
import logging

# Import CRUD operations from your db module
from ..db import crud # Assuming crud.py is in services/gateway/app/db/crud.py

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
    id: Optional[UUID] = None # Change type to UUID for consistency with DB

class ChatUpdate(ChatBase):
    pass

class ChatResponse(ChatBase):
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None # Not currently in DB schema, but good to have. If not used, remove.
    
    class Config:
        from_attributes = True

# Message models
class MessageBase(BaseModel):
    role: str  # user, assistant, system
    content: str
    parts: Optional[List[dict]] = None
    attachments: Optional[List[dict]] = [] # Ensure attachments field is present

    class Config:
        alias_generator = to_camel
        populate_by_name = True
        from_attributes = True

class MessageCreate(MessageBase):
    pass

class MessageResponse(MessageBase):
    id: UUID
    chat_id: UUID = Field(..., alias="chatId") # Use UUID type
    created_at: datetime = Field(..., alias="createdAt")

    class Config:
        from_attributes = True

# Chat routes
@router.post("/api/chats", response_model=ChatResponse, status_code=status.HTTP_201_CREATED)
async def create_chat(
    chat_data: ChatCreate, # Renamed from 'chat' to avoid conflict with model alias
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Create a new chat conversation"""
    log.info(f"Creating new chat for user {current_user['sub']}")
    
    user_id_uuid = UUID(current_user['sub']) # Convert user_id string from JWT to UUID
    chat_id_uuid = chat_data.id if chat_data.id else uuid4() # Use provided ID or generate new UUID

    # Call the CRUD function to save the chat
    try:
        db_chat = await crud.create_chat(
            db=db,
            user_id=user_id_uuid,
            chat_id=chat_id_uuid,
            title=chat_data.title,
            visibility=chat_data.visibility
        )
        return ChatResponse.model_validate(db_chat)
    except Exception as e:
        log.error(f"Error creating chat in DB: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create chat")

@router.get("/api/chats", response_model=List[ChatResponse])
async def get_chats(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Get all chats for the current user"""
    log.info(f"Fetching all chats for user {current_user['sub']}")
    user_id_uuid = UUID(current_user['sub'])

    try:
        chats_from_db = await crud.get_all_chats_for_user(db=db, user_id=user_id_uuid)
        return [ChatResponse.model_validate(chat_obj) for chat_obj in chats_from_db]
    except Exception as e:
        log.error(f"Error fetching chats from DB: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve chats")

@router.get("/api/chats/{chat_id}", response_model=ChatResponse)
async def get_chat(
    chat_id: UUID = Path(...), # Ensure path parameter is UUID type
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Get a specific chat by ID"""
    log.info(f"Fetching chat {chat_id} for user {current_user['sub']}")
    user_id_uuid = UUID(current_user['sub'])
    try:
        db_chat = await crud.get_chat_by_id(db=db, chat_id=chat_id, user_id=user_id_uuid)
        if not db_chat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found or access denied")
        return ChatResponse.model_validate(db_chat)
    except HTTPException:
        raise # Re-raise if it's already an HTTPException
    except Exception as e:
        log.error(f"Error fetching chat {chat_id} from DB: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve chat")

@router.put("/api/chats/{chat_id}", response_model=ChatResponse)
async def update_chat(
    chat_data: ChatUpdate, # Renamed from 'chat'
    chat_id: UUID = Path(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Update a chat"""
    log.info(f"Updating chat {chat_id} for user {current_user['sub']}")
    user_id_uuid = UUID(current_user['sub'])
    try:
        updated_chat = await crud.update_chat(
            db=db,
            chat_id=chat_id,
            user_id=user_id_uuid,
            title=chat_data.title,
            visibility=chat_data.visibility
        )
        if not updated_chat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found or access denied")
        return ChatResponse.model_validate(updated_chat)
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error updating chat {chat_id} in DB: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update chat")

@router.delete("/api/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
    chat_id: UUID = Path(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Delete a chat and its associated messages and memories"""
    log.info(f"Deleting chat {chat_id} for user {current_user['sub']}")
    user_id_uuid = UUID(current_user['sub'])
    try:
        deleted = await crud.delete_chat_by_id(db=db, chat_id=chat_id, user_id=user_id_uuid)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found or access denied")
        return # FastAPI will return 204 No Content
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Error deleting chat {chat_id} from DB: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete chat")

# Chat message routes
@router.post("/api/chats/{chat_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    message_data: MessageCreate, # Renamed from 'message'
    chat_id: UUID = Path(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Add a message to a chat"""
    log.info(f"Adding message to chat {chat_id} for user {current_user['sub']}")
    user_id_uuid = UUID(current_user['sub'])
    
    # First, verify the chat exists and belongs to the user
    existing_chat = await crud.get_chat_by_id(db, chat_id, user_id_uuid)
    if not existing_chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found or access denied")

    # Ensure parts and attachments are serialized to JSON strings for storage
    parts_to_save = json.dumps(message_data.parts) if message_data.parts is not None else json.dumps([{"type": "text", "text": message_data.content}])
    attachments_to_save = json.dumps(message_data.attachments) if message_data.attachments is not None else "[]" # Default to empty string for empty list

    try:
        db_message = await crud.save_chat_message(
            db=db,
            chat_id=chat_id,
            role=message_data.role,
            parts=parts_to_save,
            attachments=attachments_to_save,
            created_at=datetime.utcnow()
        )
        # For the response model, convert them back from string
        response_data = db_message.__dict__.copy()
        response_data["parts"] = json.loads(db_message.parts)
        response_data["attachments"] = json.loads(db_message.attachments)
        return MessageResponse.model_validate(response_data)
    except Exception as e:
        log.error(f"Error saving message to chat {chat_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save message")

@router.get("/api/chats/{chat_id}/messages", response_model=List[MessageResponse])
async def get_chat_messages(
    chat_id: UUID = Path(...),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """Get all messages for a specific chat"""
    log.info(f"Fetching messages for chat {chat_id} for user {current_user['sub']}")
    user_id_uuid = UUID(current_user['sub'])
    try:
        messages_from_db = await crud.get_chat_messages_by_chat_id(db=db, chat_id=chat_id, user_id=user_id_uuid)
        
        parsed_messages = []
        for msg in messages_from_db:
            msg_dict = msg.__dict__.copy()
            
            # If parts is stored as a stringified JSON, parse it here
            if isinstance(msg_dict.get("parts"), str):
                try:
                    msg_dict["parts"] = json.loads(msg_dict["parts"])
                except json.JSONDecodeError:
                    log.error(f"Failed to decode parts JSON for message {msg.id}: {msg_dict['parts']}")
                    msg_dict["parts"] = [{"type": "text", "text": "Error loading message content"}] # Fallback
            
            # Handle attachments if they are also JSON strings
            if isinstance(msg_dict.get("attachments"), str):
                try:
                    msg_dict["attachments"] = json.loads(msg_dict["attachments"])
                except json.JSONDecodeError:
                    log.error(f"Failed to decode attachments JSON for message {msg.id}: {msg_dict['attachments']}")
                    msg_dict["attachments"] = [] # Fallback
            
            # Ensure content is always the text from parts for UI compatibility
            # This might require some logic to combine parts if there are multiple.
            # For simplicity, if first part is text, use that.
            if msg_dict.get("parts") and len(msg_dict["parts"]) > 0 and msg_dict["parts"][0].get("type") == "text":
                msg_dict["content"] = msg_dict["parts"][0].get("text", "")
            else:
                msg_dict["content"] = "" # Fallback if no text part or parts are empty
            
            parsed_messages.append(MessageResponse.model_validate(msg_dict))

        return parsed_messages
    except Exception as e:
        log.error(f"Error fetching messages for chat {chat_id} from DB: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve messages")