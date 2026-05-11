"""
Cloudflare R2 document storage client.

Used by PDF ingestors to store source documents before LLM extraction.
R2 is S3-compatible — boto3 with a custom endpoint_url.

Free tier: 10GB storage, 1M Class A ops (writes), 10M Class B ops (reads) per month.
Sufficient for all of Phase 1.

Key layout: {source_id}/{year}/{document_id}.pdf
"""

import hashlib
import logging
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError

from backend.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def document_key(source_id: str, document_id: str) -> str:
    """Stable R2 object key for a source document."""
    return f"{source_id}/{document_id}"


def upload_document(
    content: bytes,
    source_id: str,
    document_id: str,
    content_type: str = "application/pdf",
) -> str:
    """
    Upload a document to R2. Returns the object key.
    Idempotent: uploading the same content twice is safe.
    """
    key = document_key(source_id, document_id)
    _r2_client().put_object(
        Bucket=settings.r2_bucket_name,
        Key=key,
        Body=content,
        ContentType=content_type,
    )
    logger.info("Uploaded %s to R2 (%d bytes)", key, len(content))
    return key


def download_document(source_id: str, document_id: str) -> bytes:
    """Download a document from R2."""
    key = document_key(source_id, document_id)
    response = _r2_client().get_object(Bucket=settings.r2_bucket_name, Key=key)
    return response["Body"].read()


def document_exists(source_id: str, document_id: str) -> bool:
    """Check if a document is already stored. Use before re-downloading PDFs."""
    key = document_key(source_id, document_id)
    try:
        _r2_client().head_object(Bucket=settings.r2_bucket_name, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise


def content_hash(content: bytes) -> str:
    """SHA-256 hex digest — use as document_id for content-addressed storage."""
    return hashlib.sha256(content).hexdigest()


def is_configured() -> bool:
    """Returns True if R2 credentials are present in config."""
    return bool(
        settings.r2_account_id
        and settings.r2_access_key_id
        and settings.r2_secret_access_key
    )
