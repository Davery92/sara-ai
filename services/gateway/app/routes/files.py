from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from fastapi.responses import StreamingResponse # Add StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession # Changed from sqlalchemy.orm.Session
from uuid import UUID
import os
import shutil
from typing import Optional
import logging # Add logging
import io # For streaming
import uuid # for uuid.uuid4()

log = logging.getLogger(__name__) # Add logger - MOVED BEFORE OPTIONAL IMPORTS

# Add imports for text extraction (optional - graceful fallback if not available)
try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    log.warning("PyPDF2 not available - PDF text extraction disabled")

try:
    from docx import Document as DocxDocument
    PYTHON_DOCX_AVAILABLE = True
except ImportError:
    PYTHON_DOCX_AVAILABLE = False
    log.warning("python-docx not available - DOCX text extraction disabled")

from ..db import models # FIXED: Use relative import for models
from ..schemas import artifacts as schemas # FIXED: Use relative import for schemas
from ..db.session import get_session # FIXED: Use relative import for get_session
from ..auth import get_current_user_id # FIXED: Use relative import for get_current_user_id
from ..minio_client import get_minio_client # Import your MinIO client
from minio import Minio # Import Minio for type hinting
from minio.error import S3Error

# Configure the uploads directory
# UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/tmp/uploads") # No longer needed for storage
# os.makedirs(UPLOAD_DIR, exist_ok=True) # No longer needed for storage

# Configure allowed file types and size limits
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "txt", "pdf", "doc", "docx"}

router = APIRouter(
    prefix="/v1/files",
    tags=["files"],
)

def get_file_extension(filename: str) -> Optional[str]:
    """Extract and return the file extension from a filename."""
    if "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    return None

def extract_text_from_upload(file_content: bytes, filename: str) -> str:
    """Extract text content from uploaded file immediately during upload."""
    ext = get_file_extension(filename)
    extracted_text = ""
    
    log.info(f"GATEWAY: Extracting text from uploaded file '{filename}' (type: {ext})")
    
    try:
        if ext == "txt":
            extracted_text = file_content.decode('utf-8', errors='ignore')
            log.info(f"GATEWAY: Extracted {len(extracted_text)} characters from TXT file")
            
        elif ext == "pdf":
            if PYPDF2_AVAILABLE:
                reader = PdfReader(io.BytesIO(file_content))
                for page in reader.pages:
                    extracted_text += page.extract_text() + "\n"
                log.info(f"GATEWAY: Extracted {len(extracted_text)} characters from PDF file")
            else:
                log.warning("GATEWAY: PyPDF2 not available - PDF text extraction disabled")
                return "[PDF text extraction unavailable - please rebuild gateway container with dependencies]"
            
        elif ext == "docx":
            if PYTHON_DOCX_AVAILABLE:
                doc = DocxDocument(io.BytesIO(file_content))
                for para in doc.paragraphs:
                    extracted_text += para.text + "\n"
                log.info(f"GATEWAY: Extracted {len(extracted_text)} characters from DOCX file")
            else:
                log.warning("GATEWAY: python-docx not available - DOCX text extraction disabled")
                return "[DOCX text extraction unavailable - please rebuild gateway container with dependencies]"
            
        elif ext == "doc":
            # Basic attempt for .doc files
            extracted_text = file_content.decode('latin-1', errors='replace')
            extracted_text = f"[Content from .doc file (may be garbled):\n{extracted_text}\n]"
            log.warning(f"GATEWAY: Basic extraction from DOC file, {len(extracted_text)} characters")
            
        else:
            log.warning(f"GATEWAY: File type '{ext}' not supported for text extraction")
            return ""
            
    except Exception as e:
        log.error(f"GATEWAY: Error extracting text from {filename}: {e}")
        return f"[Error extracting text from {filename}: {str(e)}]"
    
    if not extracted_text.strip():
        log.warning(f"GATEWAY: No text content found in {filename}")
        return "[No text content found in file]"
    
    log.info(f"GATEWAY: Successfully extracted text from {filename} - First 100 chars: {extracted_text[:100].replace(chr(10), ' ')}")
    return extracted_text.strip()

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    minio: Minio = Depends(get_minio_client), # Inject MinIO client
    current_user_id: UUID = Depends(get_current_user_id)
):
    log.info(f"GATEWAY: Received request to /v1/files/upload. Filename: {file.filename}")
    if not minio:
        raise HTTPException(status_code=503, detail="File storage service unavailable.")

    contents = await file.read() 
    file_size = len(contents)
    await file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds the {MAX_FILE_SIZE / (1024 * 1024)}MB limit"
        )
    
    ext = get_file_extension(file.filename)
    if not ext or ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    unique_filename = f"{current_user_id}/{uuid.uuid4()}.{ext}" # Prefix with user_id for organization
    bucket_name = os.getenv("MINIO_BUCKET_NAME", "sara-uploads")

    # EXTRACT TEXT CONTENT IMMEDIATELY DURING UPLOAD
    extracted_text = ""
    if ext in ["txt", "pdf", "docx", "doc"]:
        extracted_text = extract_text_from_upload(contents, file.filename)
        log.info(f"GATEWAY: Text extraction completed for {file.filename} - {len(extracted_text)} characters extracted")

    try:
        minio.put_object(
            bucket_name,
            unique_filename,
            io.BytesIO(contents), # Use BytesIO for in-memory content
            length=file_size,
            content_type=file.content_type
        )
        log.info(f"File '{unique_filename}' uploaded to MinIO bucket '{bucket_name}'.")
    except S3Error as e:
        log.error(f"MinIO S3Error uploading file: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file to storage: {str(e)}"
        )
    except Exception as e:
        log.error(f"Unexpected error uploading to MinIO: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save file due to an unexpected error."
        )

    response_data = {
        "url": f"/v1/files/{unique_filename}", 
        "pathname": unique_filename, 
        "contentType": file.content_type,
        "size": file_size,
        "original_filename": file.filename,
        "object_name": unique_filename
    }
    
    # Include extracted text in response if available
    if extracted_text:
        response_data["extracted_text"] = extracted_text
        log.info(f"GATEWAY: Including extracted text in upload response ({len(extracted_text)} characters)")
    
    return response_data

@router.get("/{user_id_str}/{file_key}") # Path now includes user_id
async def get_file(
    user_id_str: str,
    file_key: str,
    minio: Minio = Depends(get_minio_client),
    current_user_id: UUID = Depends(get_current_user_id) # For auth
):
    if not minio:
        raise HTTPException(status_code=503, detail="File storage service unavailable.")

    object_name = f"{user_id_str}/{file_key}"
    
    if str(current_user_id) != user_id_str:
         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    bucket_name = os.getenv("MINIO_BUCKET_NAME", "sara-uploads")
    try:
        response = minio.get_object(bucket_name, object_name)
        return StreamingResponse(response.stream(32*1024), media_type=response.headers.get("Content-Type"))
    except S3Error as e:
        if e.code == "NoSuchKey":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        log.error(f"MinIO S3Error getting file: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Could not retrieve file: {str(e)}")
    finally:
        if 'response' in locals() and response:
            response.close()
            response.release_conn()