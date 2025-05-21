import enum
import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Text, Boolean, Enum as SAEnum, PrimaryKeyConstraint, Uuid
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base # Assuming Base is defined in services/gateway/app/database.py

class DocumentKind(enum.Enum):
    TEXT = "text"
    CODE = "code"
    IMAGE = "image"
    SHEET = "sheet"

class Document(Base):
    __tablename__ = "documents"

    id = Column(Uuid, default=uuid.uuid4) # Main artifact identifier
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    title = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    kind = Column(SAEnum(DocumentKind), nullable=False)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False) # Assuming User table has Uuid primary key named 'id'
    # If you have a User model, you can add: # ForeignKey("users.id")

    # Composite primary key
    __table_args__ = (PrimaryKeyConstraint('id', 'created_at'), {})

    # Relationship (if suggestions are implemented)
    # suggestions = relationship("Suggestion", back_populates="document", cascade="all, delete-orphan")

class Suggestion(Base):
    __tablename__ = "suggestions"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id = Column(Uuid, nullable=False)
    document_created_at = Column(DateTime(timezone=True), nullable=False)
    original_text = Column(Text)
    suggested_text = Column(Text)
    description = Column(Text, nullable=True)
    is_resolved = Column(Boolean, default=False)
    user_id = Column(Uuid, ForeignKey("users.id"), nullable=False) # Assuming User table has Uuid primary key
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Composite foreign key to Document table
    # __table_args__ = (
    #     ForeignKeyConstraint([	document_id', 'document_created_at'],
    #                          ['documents.id', 'documents.created_at']),
    #     {}
    # )

    # document = relationship("Document", back_populates="suggestions")

# Note: 
# 1. The relationships and ForeignKeyConstraint for Suggestion are commented out 
#    as they depend on the exact setup and whether suggestions are implemented now.
# 2. The user_id ForeignKey constraint assumes a 'users' table with a Uuid 'id' column. 
#    Adjust as per your actual User model/table.
# 3. For UUIDs, using sqlalchemy.dialects.postgresql.UUID might be better if you are on PostgreSQL,
#    otherwise sqlalchemy.Uuid is a more generic choice. 