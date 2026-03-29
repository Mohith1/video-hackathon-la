"""
Storage layer with automatic local-file fallback.
If AWS_ACCESS_KEY_ID is not set (or DynamoDB is unreachable), records are
stored in ./local_db/ as JSON files so the app works fully offline / without
real AWS credentials during development.
"""
import boto3
import json
import os
from datetime import datetime
from typing import Optional
from app.config import get_settings

settings = get_settings()

LOCAL_DB_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "local_db")

def _use_local() -> bool:
    return not settings.aws_access_key_id


# ── Local filesystem store ────────────────────────────────────────────────────

def _local_path(video_id: str) -> str:
    os.makedirs(LOCAL_DB_DIR, exist_ok=True)
    return os.path.join(LOCAL_DB_DIR, f"{video_id}.json")

def _local_write(video_id: str, record: dict):
    with open(_local_path(video_id), "w") as f:
        json.dump(record, f, default=str)

def _local_read(video_id: str) -> Optional[dict]:
    p = _local_path(video_id)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)

def _local_update(video_id: str, **kwargs):
    record = _local_read(video_id) or {}
    record.update(kwargs)
    _local_write(video_id, record)


# ── DynamoDB store ────────────────────────────────────────────────────────────

def _get_dynamodb():
    return boto3.resource(
        "dynamodb",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def create_video_record(video_id: str, mode: str, s3_uri: str, filename: str):
    record = {
        "video_id": video_id,
        "status": "pending",
        "mode": mode,
        "s3_uri": s3_uri,
        "filename": filename,
        "created_at": datetime.utcnow().isoformat(),
        "progress": 0,
        "results": [],
    }
    if _use_local():
        _local_write(video_id, record)
        return
    try:
        db = _get_dynamodb()
        db.Table(settings.dynamodb_table).put_item(Item=record)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"DynamoDB unavailable ({e}), using local storage")
        _local_write(video_id, record)


def update_video_status(video_id: str, **kwargs):
    if _use_local():
        _local_update(video_id, **kwargs)
        return
    try:
        db = _get_dynamodb()
        table = db.Table(settings.dynamodb_table)
        update_expr = "SET " + ", ".join(f"#{k} = :{k}" for k in kwargs)
        expr_names  = {f"#{k}": k for k in kwargs}
        expr_values = {f":{k}": v for k, v in kwargs.items()}
        table.update_item(
            Key={"video_id": video_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"DynamoDB update failed ({e}), using local storage")
        _local_update(video_id, **kwargs)


def get_video_record(video_id: str) -> Optional[dict]:
    if _use_local():
        return _local_read(video_id)
    try:
        db = _get_dynamodb()
        resp = db.Table(settings.dynamodb_table).get_item(Key={"video_id": video_id})
        result = resp.get("Item")
        if result:
            return result
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"DynamoDB get failed ({e}), using local storage")
    return _local_read(video_id)


def ensure_table_exists():
    if _use_local():
        os.makedirs(LOCAL_DB_DIR, exist_ok=True)
        return
    client = boto3.client(
        "dynamodb",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id or None,
        aws_secret_access_key=settings.aws_secret_access_key or None,
    )
    try:
        client.describe_table(TableName=settings.dynamodb_table)
    except client.exceptions.ResourceNotFoundException:
        client.create_table(
            TableName=settings.dynamodb_table,
            KeySchema=[{"AttributeName": "video_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "video_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.get_waiter("table_exists").wait(TableName=settings.dynamodb_table)
