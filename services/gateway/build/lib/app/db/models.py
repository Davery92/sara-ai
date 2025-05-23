# services/gateway/app/db/models.py
from sqlalchemy import Column, Enum, Index, Text, DateTime, String, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import DeclarativeBase, relationship
import uuid
import enum

# --- Temporarily comment out these lines ---
from sqlalchemy.dialects.postgresql import UUID # KEEP THIS FOR NOW
# from sqlalchemy.dialects.postgresql import JSONB # <--- COMMENT OUT
# from pgvector.sqlalchemy import Vector # <--- COMMENT OUT

print("DEBUG: models.py is being imported.") # Keep this!

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
    # embedding  = Column(Vector(1024)) # <--- CHANGE THIS LINE
    embedding = Column(Text, nullable=True) # Use Text instead of Vector for now
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        Index("ix_memory_room_type_created", "room_id", "type", "created_at"),
    )

class EmbeddingMessage(Base):
    __tablename__ = "embedding_messages"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id    = Column(UUID(as_uuid=True), nullable=False, index=True)
    content    = Column(Text, nullable=False)
    # embedding  = Column(Vector(1024), nullable=True) # <--- CHANGE THIS LINE
    embedding = Column(Text, nullable=True) # Use Text instead of Vector for now
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
    # parts = Column(JSONB, nullable=False) # <--- COMMENT OUT
    parts = Column(Text, nullable=False) # Use Text instead of JSONB
    # attachments = Column(JSONB, nullable=False, default=[]) # <--- COMMENT OUT
    attachments = Column(Text, nullable=False, default="[]") # Use Text, default to string
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    chat = relationship("Chat", back_populates="messages")

__all__ = ["Base", "Memory", "EmbeddingMessage", "User", "Chat", "ChatMessage"]
print("DEBUG: models.py finished importing.") # Keep this!