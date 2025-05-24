from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc, asc, delete
from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from datetime import datetime
import json # ADDED: for json.loads/dumps

# Import all core models for CRUD operations
from ..db.models import User, Chat, ChatMessage, EmbeddingMessage, Memory, Base
# Import artifact-related models and enum
from ..models.artifacts import Document, Suggestion, DocumentKind # FIXED: Corrected import path for DocumentKind, Document, Suggestion

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

    # ADDED: Delete Documents associated with this user_id and document.id (or related to chat_id if applicable)
    # Documents might not be directly linked to chat_id, but to user_id.
    # For simplicity, we'll assume a direct delete by user_id for now if no chat_id link.
    # If documents should be deleted *only* if linked to a specific chat, more complex logic is needed.
    # For now, let's assume if a chat is deleted, its related documents are also deleted.
    # This requires adding chat_id to the Document model if it's not there, or finding another link.
    # Given the current Document model, it only has `user_id`. So deleting docs by user_id
    # would delete ALL docs for that user. This is probably not intended.
    # Let's SKIP deleting `Document` and `Suggestion` here for now, as they are independent of `Chat`.
    # They should have their own separate deletion routes (e.g., delete artifact).
    # You already have `deleteDocumentsByIdAfterTimestamp` and related logic in `artifacts.py`.
    # This CRUD is for `Chat` specific entities.

    # Finally, delete the chat itself
    await db.delete(chat_to_delete)
    await db.commit()
    return True

# --- ChatMessage Operations ---

async def save_chat_message(
    db: AsyncSession,
    chat_id: UUID,
    role: str,
    # parts and attachments are passed as JSON strings from the API route
    parts: str, # Changed type from List[Dict] to str
    attachments: str, # Changed type from List[Dict] to str
    created_at: datetime
) -> ChatMessage:
    """Saves a new message to the chat history (messages_v2 table)."""
    new_message = ChatMessage(
        chat_id=chat_id,
        role=role,
        parts=parts, # Store as string
        attachments=attachments, # Store as string
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

# ADDED CRUD functions for Document and Suggestion
async def save_document(
    db: AsyncSession,
    doc_id: UUID,
    title: str,
    kind: DocumentKind, # Use DocumentKind enum
    content: str,
    user_id: UUID,
    created_at: datetime
) -> Document:
    new_document = Document(
        id=doc_id,
        title=title,
        kind=kind.value, # Store enum value as string
        content=content,
        user_id=user_id,
        created_at=created_at
    )
    db.add(new_document)
    await db.commit()
    await db.refresh(new_document)
    return new_document

async def get_document_by_id(db: AsyncSession, doc_id: UUID, user_id: UUID) -> Optional[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id, Document.user_id == user_id)
        .order_by(desc(Document.created_at)) # Get the latest version
    )
    return result.scalars().first()

async def get_all_document_versions_by_id(db: AsyncSession, doc_id: UUID, user_id: UUID) -> List[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.id == doc_id, Document.user_id == user_id)
        .order_by(asc(Document.created_at)) # All versions, oldest first
    )
    return result.scalars().all()

async def delete_document_versions_after_timestamp(
    db: AsyncSession,
    doc_id: UUID,
    user_id: UUID,
    timestamp: datetime
) -> bool:
    # First, verify ownership for any version to prevent unauthorized deletion attempts
    owner_check = await db.execute(
        select(Document.id).where(Document.id == doc_id, Document.user_id == user_id)
    )
    if not owner_check.scalars().first():
        return False # Document not found or not owned by user

    delete_stmt = delete(Document).where(
        Document.id == doc_id,
        Document.user_id == user_id,
        Document.created_at > timestamp
    )
    result = await db.execute(delete_stmt)
    await db.commit()
    return result.rowcount > 0

async def save_suggestion(
    db: AsyncSession,
    suggestion_id: UUID,
    document_id: UUID,
    document_created_at: datetime,
    original_text: str,
    suggested_text: str,
    description: Optional[str],
    is_resolved: bool,
    user_id: UUID,
    created_at: datetime
) -> Suggestion:
    new_suggestion = Suggestion(
        id=suggestion_id,
        document_id=document_id,
        document_created_at=document_created_at,
        original_text=original_text,
        suggested_text=suggested_text,
        description=description,
        is_resolved=is_resolved,
        user_id=user_id,
        created_at=created_at
    )
    db.add(new_suggestion)
    await db.commit()
    await db.refresh(new_suggestion)
    return new_suggestion

async def get_suggestions_by_document_id(db: AsyncSession, document_id: UUID, user_id: UUID) -> List[Suggestion]:
    result = await db.execute(
        select(Suggestion)
        .where(Suggestion.document_id == document_id, Suggestion.user_id == user_id)
        .order_by(asc(Suggestion.created_at))
    )
    return result.scalars().all()

async def update_suggestion(
    db: AsyncSession,
    suggestion_id: UUID,
    user_id: UUID,
    is_resolved: Optional[bool] = None
) -> Optional[Suggestion]:
    from sqlalchemy import update as sa_update
    stmt = (
        sa_update(Suggestion)
        .where(Suggestion.id == suggestion_id, Suggestion.user_id == user_id)
        .values(is_resolved=is_resolved, created_at=datetime.utcnow())
        .returning(Suggestion) # Return the updated object
    )
    result = await db.execute(stmt)
    updated_suggestion = result.scalars().first()
    await db.commit()
    return updated_suggestion