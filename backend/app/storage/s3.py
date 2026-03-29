"""
Storage layer with automatic local-file fallback for S3.
If AWS_ACCESS_KEY_ID is not set, files are stored under ./local_uploads/
and served via the FastAPI /local-files/ static route.
Bedrock calls always use the Bearer token (no S3 credentials needed for that).
"""
import boto3
import json
import os
import shutil
import httpx
from botocore.config import Config
from app.config import get_settings

settings = get_settings()

LOCAL_UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "local_uploads")


def _use_local() -> bool:
    return not settings.aws_access_key_id


# ── Local filesystem helpers ──────────────────────────────────────────────────

def _local_path(s3_key: str) -> str:
    full = os.path.join(LOCAL_UPLOADS_DIR, s3_key.lstrip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    return full


def _local_url(s3_key: str) -> str:
    """URL served by FastAPI static mount at /local-files/"""
    base = settings.backend_public_url.rstrip("/")
    return f"{base}/local-files/{s3_key.lstrip('/')}"


# ── S3 client (only used when AWS_ACCESS_KEY_ID is set) ──────────────────────

def get_s3_client():
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )


# ── Bedrock (Bearer token, no S3 creds needed) ───────────────────────────────

def _bedrock_client():
    """
    Build a boto3 bedrock-runtime client.
    Priority:
      1. Standard credentials (ACCESS_KEY + SECRET + SESSION_TOKEN) — workshop standard
      2. Bearer token HTTP fallback
    """
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        return boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            aws_session_token=settings.aws_session_token or None,
            config=Config(
                retries={"max_attempts": 3, "mode": "adaptive"},
                read_timeout=600,
                connect_timeout=30,
            ),
        )
    # No credentials — let boto3 use environment / instance profile
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        config=Config(retries={"max_attempts": 3, "mode": "adaptive"},
                      read_timeout=600, connect_timeout=30),
    )


def invoke_bedrock_model(model_id: str, body: dict) -> dict:
    """
    Call Bedrock InvokeModel.
    Uses bearer token HTTP when set (hackathon credential), otherwise boto3 SigV4.
    """
    if settings.aws_bearer_token_bedrock:
        url = (
            f"https://bedrock-runtime.{settings.aws_region}.amazonaws.com"
            f"/model/{model_id}/invoke"
        )
        headers = {
            "Authorization": f"Bearer {settings.aws_bearer_token_bedrock}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        resp = httpx.post(url, json=body, headers=headers, timeout=600.0)
        resp.raise_for_status()
        return resp.json()

    # Fallback: standard boto3 SigV4
    client = _bedrock_client()
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(response["body"].read())


# ── Upload / Download ─────────────────────────────────────────────────────────

def upload_file_to_s3(local_path: str, s3_key: str, bucket: str = None) -> str:
    if _use_local():
        dest = _local_path(s3_key)
        shutil.copy2(local_path, dest)
        return f"local://{s3_key}"

    s3 = get_s3_client()
    bucket = bucket or settings.s3_bucket
    s3.upload_file(local_path, bucket, s3_key)
    return f"s3://{bucket}/{s3_key}"


def download_file_from_s3(s3_key: str, local_path: str, bucket: str = None):
    if _use_local():
        src = _local_path(s3_key)
        if not os.path.exists(src):
            raise FileNotFoundError(f"Local file not found: {src}")
        shutil.copy2(src, local_path)
        return

    s3 = get_s3_client()
    bucket = bucket or settings.s3_bucket
    s3.download_file(bucket, s3_key, local_path)


def put_object(key: str, body: bytes | str, content_type: str = "application/json",
               bucket: str = None):
    if _use_local():
        dest = _local_path(key)
        mode = "w" if isinstance(body, str) else "wb"
        with open(dest, mode) as f:
            f.write(body)
        return

    s3 = get_s3_client()
    bucket = bucket or settings.s3_bucket
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)


def get_object(key: str, bucket: str = None) -> bytes:
    if _use_local():
        with open(_local_path(key), "rb") as f:
            return f.read()

    s3 = get_s3_client()
    bucket = bucket or settings.s3_bucket
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def head_object(key: str, bucket: str = None) -> bool:
    """Returns True if the object exists."""
    if _use_local():
        return os.path.exists(_local_path(key))
    try:
        get_s3_client().head_object(Bucket=bucket or settings.s3_bucket, Key=key)
        return True
    except Exception:
        return False


# ── URL helpers ───────────────────────────────────────────────────────────────

def get_public_url(s3_key: str, bucket: str = None) -> str:
    if _use_local():
        return _local_url(s3_key)
    bucket = bucket or settings.s3_bucket
    return f"https://{bucket}.s3.amazonaws.com/{s3_key}"


def get_video_stream_url(s3_uri: str) -> str:
    """
    Return a URL that the browser can stream.
    For local mode: served via FastAPI /local-files/ static mount.
    For S3: tries presigned URL → access point alias → direct S3 URL.
    """
    if s3_uri.startswith("local://"):
        s3_key = s3_uri.replace("local://", "")
        return _local_url(s3_key)

    # Parse bucket + key from s3:// URI
    s3_path = s3_uri.replace("s3://", "")
    parts = s3_path.split("/", 1)
    bucket = parts[0]
    s3_key = parts[1] if len(parts) > 1 else ""

    # 1. Presigned URL (requires AWS credentials)
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        try:
            s3 = boto3.client(
                "s3",
                region_name=settings.aws_region,
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                aws_session_token=settings.aws_session_token or None,
            )
            return s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": s3_key},
                ExpiresIn=7200,
            )
        except Exception:
            pass

    # 2. Access Point alias URL (works if access point has a public read policy)
    if settings.s3_access_point_alias:
        alias = settings.s3_access_point_alias
        return (
            f"https://{alias}.s3.{settings.aws_region}.amazonaws.com/{s3_key}"
        )

    # 3. Direct bucket URL (only works if bucket/object is public)
    return f"https://{bucket}.s3.{settings.aws_region}.amazonaws.com/{s3_key}"


# ── Legacy alias ──────────────────────────────────────────────────────────────

def get_bedrock_client():
    return _bedrock_client()

def get_bedrock_client_UNUSED():
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
        config=Config(retries={"max_attempts": 3, "mode": "adaptive"},
                      read_timeout=600, connect_timeout=30),
    )
