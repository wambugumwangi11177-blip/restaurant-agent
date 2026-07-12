"""
backend/storage.py
───────────────────
Pluggable object storage (Phase 9). Local filesystem by default; S3/R2 when
STORAGE_BACKEND=s3 (needs boto3 + bucket env). Gives any future upload feature
(menu photos, receipts) a stable save/load/url/delete interface, so moving to
cloud object storage is an env change, not a code change — the same "code half is
ready, provisioning is your flip" pattern as the Redis-ready rate limiter.

Local backend is fully functional and tested. The S3 branch is only exercised
when STORAGE_BACKEND=s3 is configured; boto3 is imported lazily so it stays an
optional dependency.
"""

import os
import pathlib
import uuid

_BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()
_LOCAL_ROOT = pathlib.Path(
    os.getenv("STORAGE_LOCAL_ROOT", os.path.join(os.path.dirname(__file__), ".storage"))
)
_S3_BUCKET = os.getenv("STORAGE_S3_BUCKET", "")
_S3_PUBLIC_BASE = os.getenv("STORAGE_S3_PUBLIC_BASE", "")  # e.g. https://cdn.example.com


def _s3_client():
    import boto3  # lazy: optional dependency, only needed for the s3 backend
    return boto3.client("s3")


def save(data: bytes, key: str | None = None, content_type: str = "application/octet-stream") -> str:
    """Store `data` and return its key. A key is generated if not supplied."""
    key = key or uuid.uuid4().hex
    if _BACKEND == "s3":
        _s3_client().put_object(Bucket=_S3_BUCKET, Key=key, Body=data, ContentType=content_type)
    else:
        path = _LOCAL_ROOT / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return key


def load(key: str) -> bytes:
    if _BACKEND == "s3":
        return _s3_client().get_object(Bucket=_S3_BUCKET, Key=key)["Body"].read()
    return (_LOCAL_ROOT / key).read_bytes()


def exists(key: str) -> bool:
    if _BACKEND == "s3":
        try:
            _s3_client().head_object(Bucket=_S3_BUCKET, Key=key)
            return True
        except Exception:
            return False
    return (_LOCAL_ROOT / key).exists()


def url(key: str) -> str:
    """A retrievable URL for `key`. S3: public base if set, else the s3:// URI;
    local: a stable app route a future handler can serve from."""
    if _BACKEND == "s3":
        if _S3_PUBLIC_BASE:
            return f"{_S3_PUBLIC_BASE.rstrip('/')}/{key}"
        return f"s3://{_S3_BUCKET}/{key}"
    return f"/files/{key}"


def delete(key: str) -> None:
    if _BACKEND == "s3":
        _s3_client().delete_object(Bucket=_S3_BUCKET, Key=key)
    else:
        (_LOCAL_ROOT / key).unlink(missing_ok=True)
