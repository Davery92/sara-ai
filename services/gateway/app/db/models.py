from sqlalchemy import Column, Enum, Index, Text, DateTime
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import DeclarativeBase
import uuid
import enum

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
    embedding  = Column(Vector(1024))  # ✅ pgvector defined properly
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_memory_room_type_created", "room_id", "type", "created_at"),
    )
class Message(Base):
    __tablename__ = "message"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    room_id    = Column(UUID(as_uuid=True), nullable=False, index=True)
    content    = Column(Text, nullable=False)      # or rename to `text` if tests expect that
    embedding  = Column(Vector(1024), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_message_room_created", "room_id", "created_at"),
    )
# at bottom of models.py
__all__ = ["Base", "Memory", "Message"]
