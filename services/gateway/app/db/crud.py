# services/gateway/app/db/crud.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, asc, delete
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime

# Import all models needed for CRUD operations
from ..db.models import User, Chat, ChatMessage, EmbeddingMessage, Memory, Base # Assuming User is also in models.py

# --- Chat Operations ---

async def create_chat(
    db: AsyncSession,
    user_id: UUID,
    chat_id: UUID, # Allow chat_id to be provided (e.g., from frontend)
    title: str,
    visibility: str # Should match the enum in your Chat model (e.g., "private", "public")
) -> Chat:
    """Creates a new chat conversation in the database."""
    new_chat = Chat(
        id=chat_id,
        user_id=user_id,
        title=title,
        visibility=visibility,
        created_at=datetime.utcnow() # Ensure creation timestamp is set
    )
    db.add(new_chat)
    await db.commit()
    await db.refresh(new_chat)
    return new_chat

async def get_chat_by_id(db: AsyncSession, chat_id: UUID, user_id: UUID) -> Optional[Chat]:
    """Retrieves a single chat by its ID for a specific user."""
    result = await db.execute(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
    )
    return result.scalars().first()

async def get_all_chats_for_user(db: AsyncSession, user_id: UUID) -> List[Chat]:
    """Retrieves all chat conversations for a given user, ordered by creation time."""
    result = await db.execute(
        select(Chat).where(Chat.user_id == user_id).order_by(desc(Chat.created_at))
    )
    return result.scalars().all()

async def update_chat(
    db: AsyncSession,
    chat_id: UUID,
    user_id: UUID,
    title: Optional[str] = None,
    visibility: Optional[str] = None
) -> Optional[Chat]:
    """Updates the title or visibility of an existing chat."""
    chat_to_update = await get_chat_by_id(db, chat_id, user_id)
    if not chat_to_update:
        return None

    if title is not None:
        chat_to_update.title = title
    if visibility is not None:
        chat_to_update.visibility = visibility

    await db.commit()
    await db.refresh(chat_to_update)
    return chat_to_update

async def delete_chat_by_id(db: AsyncSession, chat_id: UUID, user_id: UUID) -> bool:
    """
    Deletes a chat and its associated messages (ChatMessage and EmbeddingMessage)
    and memories from the database.
    Returns True if the chat was found and deleted, False otherwise.
    """
    # First, ensure the chat exists and belongs to the user
    chat_to_delete = await get_chat_by_id(db, chat_id, user_id)
    if not chat_to_delete:
        return False

    # Cascading deletes might be handled by SQLAlchemy relationships (cascade="all, delete-orphan")
    # on Chat.messages and Chat.embedding_messages (if you set them up).
    # If not, or for other related tables (like Memory for that room_id), delete manually:
    
    # Delete ChatMessages associated with this chat
    await db.execute(delete(ChatMessage).where(ChatMessage.chat_id == chat_id))
    
    # Delete EmbeddingMessages associated with this room_id (assuming room_id == chat_id for embedding messages)
    await db.execute(delete(EmbeddingMessage).where(EmbeddingMessage.room_id == chat_id))

    # Delete Memories associated with this room_id (assuming room_id == chat_id for memories)
    await db.execute(delete(Memory).where(Memory.room_id == chat_id))

    # Finally, delete the chat itself
    await db.delete(chat_to_delete)
    await db.commit()
    return True

# --- ChatMessage Operations ---

async def save_chat_message(
    db: AsyncSession,
    chat_id: UUID,
    role: str,
    parts: List[Dict],
    attachments: List[Dict],
    created_at: datetime
) -> ChatMessage:
    """Saves a new message to the chat history (messages_v2 table)."""
    new_message = ChatMessage(
        chat_id=chat_id,
        role=role,
        parts=parts,
        attachments=attachments,
        created_at=created_at
    )
    db.add(new_message)
    await db.commit()
    await db.refresh(new_message)
    return new_message

async def get_chat_messages_by_chat_id(db: AsyncSession, chat_id: UUID, user_id: UUID) -> List[ChatMessage]:
    """
    Retrieves all messages for a given chat ID.
    Includes an authorization check to ensure the user owns the chat.
    """
    # First, ensure the chat exists and belongs to the user
    chat_obj = await get_chat_by_id(db, chat_id, user_id)
    if not chat_obj:
        return [] # Return empty list if chat not found or unauthorized

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.chat_id == chat_id)
        .order_by(asc(ChatMessage.created_at))
    )
    return result.scalars().all()

# --- User Operations (minimal for auth lookup) ---

async def get_user_by_username(db: AsyncSession, username: str) -> Optional[User]:
    """Retrieves a user by their username."""
    result = await db.execute(
        select(User).where(User.username == username)
    )
    return result.scalars().first()

async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """Retrieves a user by their UUID."""
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalars().first()