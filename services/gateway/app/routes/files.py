from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession # Changed from sqlalchemy.orm.Session
from uuid import UUID
import os
import shutil
from typing import Optional

from ..db import models # FIXED: Use relative import for models
from ..schemas import artifacts as schemas # FIXED: Use relative import for schemas
from ..db.session import get_session # FIXED: Use relative import for get_session
from ..auth import get_current_user_id # FIXED: Use relative import for get_current_user_id

# Configure the uploads directory
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/tmp/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Configure allowed file types and size limits
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}

router = APIRouter(
    prefix="/v1/files",
    tags=["files"],
)

def get_file_extension(filename: str) -> Optional[str]:
    """Extract and return the file extension from a filename."""
    if "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    return None

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session), # Use AsyncSession
    current_user_id: UUID = Depends(get_current_user_id) # Use UUID type
):
    """
    Upload a file to the server.
    The file is saved to the configured uploads directory.
    Returns the file URL and metadata.
    """
    # Validate file size
    file_size = 0
    contents = await file.read()
    file_size = len(contents)
    await file.seek(0)  # Reset file pointer to beginning
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds the {MAX_FILE_SIZE / (1024 * 1024)}MB limit"
        )
    
    # Validate file extension
    ext = get_file_extension(file.filename)
    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Generate unique filename to prevent collisions
    unique_filename = f"{uuid.uuid4()}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    
    # Save the file
    try:
        with open(file_path, "wb") as buffer:
            buffer.write(contents)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )
    
    # Create a public URL
    # In production, this would be a proper URL pointing to your file server or CDN
    file_url = f"/v1/files/{unique_filename}"
    
    # Return file metadata
    return {
        "url": file_url,
        "pathname": unique_filename,
        "contentType": file.content_type,
        "size": file_size
    }

@router.get("/{filename}")
async def get_file(
    filename: str,
    current_user_id: UUID = Depends(get_current_user_id) # Use UUID type
):
    """
    Retrieve a file by filename.
    This endpoint can be used to serve the uploaded files directly,
    but in production, you would typically use a dedicated file server or CDN.
    """
    file_path = os.path.join(UPLOAD_DIR, filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    # In a real implementation, you would use a proper file response
    # with correct content type and other headers
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"file_path": file_path}
    )