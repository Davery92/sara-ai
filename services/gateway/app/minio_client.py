import os
import logging
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)

_minio_client: Minio | None = None

def get_minio_client() -> Minio | None:
    global _minio_client
    if _minio_client is None:
        try:
            endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
            access_key = os.getenv("MINIO_ACCESS_KEY")
            secret_key = os.getenv("MINIO_SECRET_KEY")
            secure_str = os.getenv("MINIO_SECURE", "false").lower()
            secure = secure_str == 'true'

            if not all([access_key, secret_key]):
                logger.error("MinIO access key or secret key not configured.")
                return None
            
            _minio_client = Minio(
                endpoint,
                access_key=access_key,
                secret_key=secret_key,
                secure=secure
            )
            logger.info(f"MinIO client initialized for endpoint: {endpoint}, secure: {secure}")
            
            # Verify connection by trying to list buckets (optional)
            # try:
            #     _minio_client.list_buckets() 
            #     logger.info("Successfully connected to MinIO and listed buckets.")
            # except Exception as e:
            #     logger.error(f"MinIO client created, but could not connect or list buckets: {e}")
            #     _minio_client = None # Invalidate client if connection check fails
            
        except Exception as e:
            logger.error(f"Failed to initialize MinIO client: {e}")
            _minio_client = None
    return _minio_client

async def ensure_bucket_exists(bucket_name: str):
    client = get_minio_client()
    if client:
        try:
            found = client.bucket_exists(bucket_name)
            if not found:
                client.make_bucket(bucket_name)
                logger.info(f"Bucket '{bucket_name}' created successfully.")
            else:
                logger.info(f"Bucket '{bucket_name}' already exists.")
        except S3Error as e:
            logger.error(f"Error ensuring bucket '{bucket_name}' exists: {e}")
    else:
        logger.error("Cannot ensure bucket exists: MinIO client not available.") 