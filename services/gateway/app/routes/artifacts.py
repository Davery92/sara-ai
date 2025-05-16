from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Annotated
import uuid
from datetime import datetime

from .. import models, schemas # Updated to use relative imports for models and schemas
from ..database import get_db
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
def create_or_update_artifact_version(
    artifact_id: uuid.UUID,
    document_data: schemas.DocumentCreate,
    db: Session = Depends(get_db),
    current_user_id: uuid.UUID = Depends(get_current_user_id) # Assume this returns the user's UUID
):
    """
    Creates a new version of an artifact. If it's the first version for this artifact_id,
    it effectively creates the artifact.
    The `artifact_id` in the path is the main identifier for an artifact across versions.
    A new `created_at` timestamp is automatically generated for each version.
    """
    db_document = models.artifacts.Document(
        id=artifact_id,
        title=document_data.title,
        content=document_data.content,
        kind=document_data.kind,
        user_id=current_user_id
        # created_at is handled by server_default in the model
    )
    db.add(db_document)
    db.commit()
    db.refresh(db_document)
    return db_document

@router.get("/{artifact_id}", response_model=List[schemas.DocumentResponse])
def get_all_artifact_versions(
    artifact_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user_id: uuid.UUID = Depends(get_current_user_id) # For authorization
):
    """
    Retrieves all Document records (versions) matching the artifact_id, ordered by created_at.
    Requires authentication and authorization (user should own the document).
    """
    documents = (
        db.query(models.artifacts.Document)
        .filter(models.artifacts.Document.id == artifact_id)
        .filter(models.artifacts.Document.user_id == current_user_id) # Authorization check
        .order_by(models.artifacts.Document.created_at.desc()) # Or .asc() depending on desired order
        .all()
    )
    if not documents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact with id {artifact_id} not found or access denied."
        )
    return documents

@router.delete("/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_artifact_versions_after_timestamp(
    artifact_id: uuid.UUID,
    timestamp: Annotated[datetime, Query(description="Delete versions created strictly after this timestamp (ISO format).")],
    db: Session = Depends(get_db),
    current_user_id: uuid.UUID = Depends(get_current_user_id)
):
    """
    Deletes Document records for the given artifact_id where created_at is greater than 
    the provided timestamp. Also deletes related Suggestion records (if implemented and cascaded).
    Requires authentication and authorization.
    """
    # First, verify the user owns at least one version of the artifact to be allowed to delete any version
    # A more granular check might be needed depending on requirements (e.g., can only delete own versions)
    owner_check = (
        db.query(models.artifacts.Document)
        .filter(models.artifacts.Document.id == artifact_id)
        .filter(models.artifacts.Document.user_id == current_user_id)
        .first()
    )
    if not owner_check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact with id {artifact_id} not found or you do not have permission to modify it."
        )

    # Proceed with deletion
    delete_statement = (
        models.artifacts.Document.__table__.delete()
        .where(models.artifacts.Document.id == artifact_id)
        .where(models.artifacts.Document.user_id == current_user_id) # Ensure user can only delete their own
        .where(models.artifacts.Document.created_at > timestamp)
    )
    result = db.execute(delete_statement)
    db.commit()

    if result.rowcount == 0:
        # This could mean no versions matched the criteria, or the artifact didn't exist/belong to user initially.
        # The initial owner_check should catch non-existence/permission issues for the artifact_id as a whole.
        # If owner_check passed but rowcount is 0, it means no versions were *after* the given timestamp.
        # Raising a 404 here might be misleading if the artifact exists but no versions matched the timestamp criteria.
        # Consider if a different response or no specific error is better if no rows are deleted.
        # For now, let's assume if owner_check passed, a 204 is fine even if 0 rows deleted by this query.
        pass 
    
    # If you implement suggestions with cascade delete, they should be handled by the DB.
    # Otherwise, you would manually delete related suggestions here:
    # db.query(models.Suggestion).filter(...).delete()
    # db.commit()

    return # FastAPI will return 204 No Content

# Placeholder for get_current_user_id. You need to implement this based on your auth setup.
# It should extract the user ID (UUID) from the token.
# Example from your ws.py (you'll need _SECRET, _ALG, jwt library):
# import jwt
# from fastapi import Header, HTTPException
# _SECRET = "your-secret"
# _ALG = "HS256"
# async def get_current_user_id(authorization: str = Header(None)) -> uuid.UUID:
#     if not authorization:
#         raise HTTPException(status_code=401, detail="Not authenticated")
#     parts = authorization.split()
#     if parts[0].lower() != "bearer" or len(parts) == 1 or len(parts) > 2:
#         raise HTTPException(status_code=401, detail="Invalid authentication header")
#     token = parts[1]
#     try:
#         payload = jwt.decode(token, _SECRET, algorithms=[_ALG])
#         user_id_str = payload.get("sub")
#         if user_id_str is None:
#             raise HTTPException(status_code=401, detail="Invalid token: sub missing")
#         return uuid.UUID(user_id_str)
#     except jwt.ExpiredSignatureError:
#         raise HTTPException(status_code=401, detail="Token has expired")
#     except jwt.InvalidTokenError:
#         raise HTTPException(status_code=401, detail="Invalid token")
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Auth error: {str(e)}")

# You would also need to update services/gateway/app/auth.py or a similar file
# with the actual get_current_user_id implementation.

# To make this router accessible, you'll need to include it in your main FastAPI app.
# For example, in your main app file (e.g., services/gateway/app/main.py):
# from .routes import artifacts
# app.include_router(artifacts.router) 