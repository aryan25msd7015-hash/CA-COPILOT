"""AWS S3 service for pre-signed URL generation and direct byte transfers."""
import boto3
from botocore.exceptions import ClientError
from app.config import settings


def _client():
    return boto3.client("s3", region_name=settings.AWS_REGION)


def generate_presigned_put_url(key: str, content_type: str = "application/pdf",
                               expires: int = 300) -> str:
    """Generate a pre-signed PUT URL for direct browser-to-S3 upload."""
    return _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key,
                "ContentType": content_type},
        ExpiresIn=expires,
    )


def generate_presigned_get_url(key: str, expires: int = 3600) -> str:
    """Generate a pre-signed GET URL for temporary document access."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key},
        ExpiresIn=expires,
    )


def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    """Upload raw bytes directly to S3 (used by WhatsApp media ingestion)."""
    _client().put_object(
        Bucket=settings.S3_BUCKET, Key=key,
        Body=data, ContentType=content_type,
    )


def download_bytes(key: str) -> bytes:
    """Download an S3 object and return its bytes."""
    response = _client().get_object(Bucket=settings.S3_BUCKET, Key=key)
    return response["Body"].read()


def get_s3_url(key: str) -> str:
    """Return the public S3 URL (for Azure OCR which needs a URL, not bytes)."""
    return f"https://{settings.S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{key}"
