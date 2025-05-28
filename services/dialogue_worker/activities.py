import os
import logging
from temporalio import activity
from pypdf2 import PdfReader
from docx import Document as DocxDocument
import io
from minio import Minio
from minio.error import S3Error

log = logging.getLogger(__name__)

# MinIO client setup
MINIO_ENDPOINT_ACT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY_ACT = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY_ACT = os.getenv("MINIO_SECRET_KEY")
MINIO_BUCKET_NAME_ACT = os.getenv("MINIO_BUCKET_NAME", "sara-uploads")
MINIO_SECURE_ACT_STR = os.getenv("MINIO_SECURE", "false").lower()
MINIO_SECURE_ACT = MINIO_SECURE_ACT_STR == 'true'

minio_client_act = None
if MINIO_ACCESS_KEY_ACT and MINIO_SECRET_KEY_ACT:
    try:
        minio_client_act = Minio(
            MINIO_ENDPOINT_ACT,
            access_key=MINIO_ACCESS_KEY_ACT,
            secret_key=MINIO_SECRET_KEY_ACT,
            secure=MINIO_SECURE_ACT
        )
        log.info(f"MinIO client for activities initialized: {MINIO_ENDPOINT_ACT}, secure={MINIO_SECURE_ACT}")
    except Exception as e:
        log.error(f"Failed to initialize MinIO client for activities: {e}")
else:
    log.error("MinIO client for activities not configured properly. Missing access or secret key.")


@activity.defn
async def extract_text_from_file_activity(object_name: str, original_filename: str) -> str:
    activity.heartbeat()
    log.info(f"Attempting to extract text from MinIO object: {object_name} (original: {original_filename})")

    if not minio_client_act:
        log.error("MinIO client not available in extract_text_from_file_activity.")
        raise Exception("File storage service not configured for text extraction.")

    response = None # Initialize response to None
    try:
        response = minio_client_act.get_object(MINIO_BUCKET_NAME_ACT, object_name)
        file_content = response.read()
    except S3Error as e:
        log.error(f"MinIO S3Error getting object {object_name}: {e}")
        raise Exception(f"Could not retrieve file from storage: {e.code}")
    finally:
        if response:
            response.close()
            response.release_conn()

    ext = original_filename.split('.')[-1].lower() if '.' in original_filename else ""
    extracted_text = ""

    if ext == "txt":
        try:
            extracted_text = file_content.decode('utf-8', errors='ignore')
        except Exception as e:
            log.error(f"Error decoding TXT file {original_filename}: {e}")
            extracted_text = f"[Error decoding TXT content: {e}]"
    elif ext == "pdf":
        try:
            reader = PdfReader(io.BytesIO(file_content))
            for page in reader.pages:
                extracted_text += page.extract_text() + "\n"
        except Exception as e:
            log.error(f"Error extracting text from PDF {original_filename}: {e}")
            extracted_text = f"[Error extracting PDF content: {e}]"
    elif ext == "docx":
        try:
            doc = DocxDocument(io.BytesIO(file_content))
            for para in doc.paragraphs:
                extracted_text += para.text + "\n"
        except Exception as e:
            log.error(f"Error extracting text from DOCX {original_filename}: {e}")
            extracted_text = f"[Error extracting DOCX content: {e}]"
    elif ext == "doc": 
        log.warning(f".doc file ({original_filename}) processing is not fully supported. Attempting plain text decode.")
        try:
            # This is a very basic attempt; proper .doc parsing is complex
            extracted_text = file_content.decode('latin-1', errors='replace') # Try latin-1 or cp1252 for older .doc
            extracted_text = f"[Content from .doc file (may be garbled or incomplete):
{extracted_text}

        except Exception as e:
            log.error(f"Error decoding .doc file {original_filename} as plain text: {e}")
            extracted_text = "[Could not extract text from .doc file]"
    else:
        log.warning(f"Unsupported file type for text extraction: {ext} (from filename: {original_filename})")
        return f"[File type '{ext}' not supported for text extraction]"

    if not extracted_text.strip(): # Check if extracted text is empty or only whitespace
        log.warning(f"No text could be extracted from {original_filename} (type: {ext}). It might be empty or an image-based file.")
        extracted_text = "[No text content found in file]"

    log.info(f"Extracted text from {original_filename} (first 100 chars): {extracted_text[:100].replace('\n', ' ')}...")
    return extracted_text 