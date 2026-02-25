"""AWS S3 file storage service (replaces Vercel Blob)."""

import boto3
from botocore.exceptions import ClientError

from app.config import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        if not settings.aws_access_key_id or not settings.aws_secret_access_key:
            raise RuntimeError("AWS S3 credentials not configured")
        _client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_s3_region,
        )
    return _client


async def upload_file(key: str, data: bytes, content_type: str) -> str:
    """Upload a file to S3 and return the public URL."""
    client = _get_client()
    client.put_object(
        Bucket=settings.aws_s3_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return f"https://{settings.aws_s3_bucket}.s3.{settings.aws_s3_region}.amazonaws.com/{key}"


async def download_file(key: str):
    """Download a file from S3. Returns (body_stream, content_type, content_length) or None."""
    client = _get_client()
    try:
        response = client.get_object(Bucket=settings.aws_s3_bucket, Key=key)
        return (
            response["Body"],
            response["ContentType"],
            response["ContentLength"],
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return None
        raise


async def delete_file(url: str) -> None:
    """Delete a file from S3 by its URL."""
    client = _get_client()
    # Extract key from URL
    prefix = f"https://{settings.aws_s3_bucket}.s3.{settings.aws_s3_region}.amazonaws.com/"
    if url.startswith(prefix):
        key = url[len(prefix):]
    else:
        # Fallback: try to extract key from the path portion
        from urllib.parse import urlparse
        parsed = urlparse(url)
        key = parsed.path.lstrip("/")

    try:
        client.delete_object(Bucket=settings.aws_s3_bucket, Key=key)
    except ClientError:
        pass  # Best effort
