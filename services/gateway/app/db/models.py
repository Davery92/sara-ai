# services/gateway/app/db/models.py
from sqlalchemy import Column, Enum, Index, Text, DateTime, String, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import DeclarativeBase, relationship
import uuid
import enum

# Corrected Imports:
from sqlalchemy.dialects.postgresql import UUID, JSONB # ADDED JSONB import
from pgvector.sqlalchemy import Vector # ADDED Vector import

print("DEBUG: models.py is being imported.")

class Base(DeclarativeBase):
    pass

class MessageType(enum.Enum):
    raw = "raw"
    summary = "summary"

class Memory(Base):
    __tablename__ = "memory"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id    = Column(UUID(as_uuid=True), nullable=False, index=True)
    type       = Column(Enum(MessageType), nullable=False, default=MessageType.raw)
    text       = Column(Text, nullable=False)
    embedding  = Column(Vector(1024), nullable=True) # FIXED: Changed back to Vector(1024)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("ix_memory_room_type_created", "room_id", "type", "created_at"),
    )

class EmbeddingMessage(Base):
    __tablename__ = "embedding_messages"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id    = Column(UUID(as_uuid=True), nullable=False, index=True)
    content    = Column(Text, nullable=False)
    embedding  = Column(Vector(1024), nullable=True) # FIXED: Changed back to Vector(1024)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("ix_message_room_created", "room_id", "created_at"),
    )

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Chat(Base):
    __tablename__ = "chats"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    title = Column(Text, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    visibility = Column(String, default="private", nullable=False)
    user = relationship("User", backref="chats")
    messages = relationship("ChatMessage", back_populates="chat", cascade="all, delete-orphan")

class ChatMessage(Base):
    __tablename__ = "messages_v2"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id"), nullable=False, index=True)
    role = Column(String, nullable=False)
    parts = Column(JSONB, nullable=False) # FIXED: Changed back to JSONB
    attachments = Column(JSONB, nullable=False, default=[]) # FIXED: Changed back to JSONB, default to empty list
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    chat = relationship("Chat", back_populates="messages")

class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    kind = Column(String(50), nullable=False, default="text")  # e.g., "text", "code", "markdown"
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    user = relationship("User", backref="documents")

__all__ = ["Base", "Memory", "EmbeddingMessage", "User", "Chat", "ChatMessage", "Document"]
print("DEBUG: models.py finished importing.")
