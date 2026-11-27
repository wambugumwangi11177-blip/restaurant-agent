"""
Pluggable object storage for uploads (delivery photos, handover, waste, zone photos).

Backends:
  - ``local`` (default): dev fallback under STORAGE_LOCAL_ROOT
  - ``s3``: any S3-compatible API (AWS S3, Cloudflare R2, Railway bucket, MinIO)
"""

from __future__ import annotations

import os
import pathlib
import uuid

_BACKEND = os.getenv("STORAGE_BACKEND", "local").lower().strip()
_LOCAL_ROOT = pathlib.Path(
    os.getenv("STORAGE_LOCAL_ROOT", os.path.join(os.path.dirname(__file__), ".storage"))
)
_S3_BUCKET = os.getenv("STORAGE_S3_BUCKET", "").strip()
_S3_PUBLIC_BASE = os.getenv("STORAGE_S3_PUBLIC_BASE", "").strip()


def _use_s3() -> bool:
    if _BACKEND == "s3":
        return bool(_S3_BUCKET)
    if os.getenv("STORAGE_PREFER_S3", "").strip().lower() in ("1", "true", "yes"):
        return bool(_S3_BUCKET)
    return False


def _s3_client():
    import boto3
    from botocore.config import Config

    endpoint = os.getenv("STORAGE_S3_ENDPOINT_URL", "").strip()
    region = os.getenv("STORAGE_S3_REGION", os.getenv("AWS_DEFAULT_REGION", "auto")).strip() or "auto"
    access = os.getenv("STORAGE_S3_ACCESS_KEY_ID", os.getenv("AWS_ACCESS_KEY_ID", "")).strip()
    secret = os.getenv("STORAGE_S3_SECRET_ACCESS_KEY", os.getenv("AWS_SECRET_ACCESS_KEY", "")).strip()
    force_path = os.getenv("STORAGE_S3_FORCE_PATH_STYLE", "").strip().lower() in ("1", "true", "yes")
    kwargs: dict = {"region_name": region}
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    if access and secret:
        kwargs["aws_access_key_id"] = access
        kwargs["aws_secret_access_key"] = secret
    config = Config(signature_version="s3v4", s3={"addressing_style": "path" if force_path else "auto"})
    return boto3.client("s3", config=config, **kwargs)


def save(data: bytes, key: str | None = None, content_type: str = "application/octet-stream") -> str:
    key = key or uuid.uuid4().hex
    if _use_s3():
        _s3_client().put_object(Bucket=_S3_BUCKET, Key=key, Body=data, ContentType=content_type)
    else:
        path = _LOCAL_ROOT / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return key


def load(key: str) -> bytes:
    if _use_s3():
        return _s3_client().get_object(Bucket=_S3_BUCKET, Key=key)["Body"].read()
    return (_LOCAL_ROOT / key).read_bytes()


def exists(key: str) -> bool:
    if _use_s3():
        try:
            _s3_client().head_object(Bucket=_S3_BUCKET, Key=key)
            return True
        except Exception:
            return False
    return (_LOCAL_ROOT / key).exists()


def url(key: str) -> str:
    if _use_s3():
        if _S3_PUBLIC_BASE:
            return f"{_S3_PUBLIC_BASE.rstrip('/')}/{key}"
        return f"s3://{_S3_BUCKET}/{key}"
    return f"/files/{key}"


def delete(key: str) -> None:
    if _use_s3():
        _s3_client().delete_object(Bucket=_S3_BUCKET, Key=key)
    else:
        (_LOCAL_ROOT / key).unlink(missing_ok=True)