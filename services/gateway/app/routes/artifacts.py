from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession # Changed from sqlalchemy.orm.Session
from typing import List, Annotated
from uuid import UUID
from datetime import datetime

from ..db import models # FIXED: Use relative import for models module
from ..schemas import artifacts as schemas # FIXED: Use relative import for schemas module
from ..db.session import get_session # FIXED: Use relative import for get_session
from ..auth import get_current_user_id # Placeholder for your auth logic
from dotenv import load_dotenv
import os

env_path = os.path.join(os.path.dirname(__file__), '../../../.env')
load_dotenv(dotenv_path=env_path)

router = APIRouter(
    prefix="/v1/artifacts",
    tags=["artifacts"],
)

@router.post("/{artifact_id}", response_model=schemas.DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_artifact_version( # Make it async
    artifact_id: UUID, # Use UUID type directly
    document_data: schemas.DocumentCreate,
    db: AsyncSession = Depends(get_session), # Use AsyncSession
    current_user_id: UUID = Depends(get_current_user_id) # Assume this returns the user's UUID
):
    """
    Creates a new version of an artifact. If it's the first version for this artifact_id,
    it effectively creates the artifact.
    The `artifact_id` in the path is the main identifier for an artifact across versions.
    A new `created_at` timestamp is automatically generated for each version.
    """
    db_document = models.Document( # Use models.Document from .db.models
        id=artifact_id,
        title=document_data.title,
        content=document_data.content,
        kind=document_data.kind.value, # Access enum value
        user_id=current_user_id,
        created_at=datetime.utcnow() # Manually set for composite primary key consistency
    )
    db.add(db_document)
    await db.commit() # Use await
    await db.refresh(db_document) # Use await
    return db_document

@router.get("/{artifact_id}", response_model=List[schemas.DocumentResponse])
async def get_all_artifact_versions( # Make it async
    artifact_id: UUID, # Use UUID type directly
    db: AsyncSession = Depends(get_session), # Use AsyncSession
    current_user_id: UUID = Depends(get_current_user_id) # For authorization
):
    """
    Retrieves all Document records (versions) matching the artifact_id, ordered by created_at.
    Requires authentication and authorization (user should own the document).
    """
    # Use await db.execute and result.scalars().all() for async
    from sqlalchemy.future import select # Import select
    documents = (
        (await db.execute(
            select(models.Document)
            .filter(models.Document.id == artifact_id)
            .filter(models.Document.user_id == current_user_id) # Authorization check
            .order_by(models.Document.created_at.desc()) # Or .asc() depending on desired order
        )).scalars().all()
    )
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact with id {artifact_id} not found or access denied."
        )
    return documents

@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact_versions_after_timestamp( # Make it async
    artifact_id: UUID, # Use UUID type directly
    timestamp: Annotated[datetime, Query(description="Delete versions created strictly after this timestamp (ISO format).")],
    db: AsyncSession = Depends(get_session), # Use AsyncSession
    current_user_id: UUID = Depends(get_current_user_id)
):
    """
    Deletes Document records for the given artifact_id where created_at is greater than 
    the provided timestamp. Also deletes related Suggestion records (if implemented and cascaded).
    Requires authentication and authorization.
    """
    from sqlalchemy.future import select # Import select
    # First, verify the user owns at least one version of the artifact to be allowed to delete any version
    owner_check = (
        (await db.execute(
            select(models.Document.id) # Only select id for existence check
            .filter(models.Document.id == artifact_id)
            .filter(models.Document.user_id == current_user_id)
        )).scalars().first()
    )
    if not owner_check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact with id {artifact_id} not found or you do not have permission to modify it."
        )

    # Proceed with deletion
    from sqlalchemy import delete # Import delete
    delete_statement = (
        delete(models.Document) # Correct way to delete from a model
        .where(models.Document.id == artifact_id)
        .where(models.Document.user_id == current_user_id) # Ensure user can only delete their own
        .where(models.Document.created_at > timestamp)
    )
    result = await db.execute(delete_statement) # Use await
    await db.commit() # Use await

    return # FastAPI will return 204 No Content