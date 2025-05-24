from pydantic import BaseModel, UUID4
from datetime import datetime
from typing import List, Optional
from ..models.artifacts import DocumentKind # FIXED: Corrected import path for DocumentKind

# Document Schemas
class DocumentBase(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    kind: DocumentKind

class DocumentCreate(DocumentBase):
    pass

class DocumentUpdate(DocumentBase):
    pass

class DocumentResponse(DocumentBase):
    id: UUID4
    created_at: datetime
    user_id: UUID4

    class Config:
        from_attributes = True

# Suggestion Schemas (Optional, if implementing suggestions)
class SuggestionBase(BaseModel):
    original_text: str
    suggested_text: str
    description: Optional[str] = None
    is_resolved: bool = False

class SuggestionCreate(SuggestionBase):
    document_id: UUID4
    document_created_at: datetime # To identify the specific document version

class SuggestionResponse(SuggestionBase):
    id: UUID4
    document_id: UUID4
    document_created_at: datetime
    user_id: UUID4
    created_at: datetime

    class Config:
        from_attributes = True