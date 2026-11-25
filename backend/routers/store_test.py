"""Test-stack helpers (gated by SEED_TEST_DATA)."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

import auth
import models
from database import get_db
from leviii_test_seed import SeedError, reset_jack_empty_journey
from routers.deps import get_or_create_restaurant
from urllib.parse import urlparse

import storage
from services import engine_triggers

router = APIRouter(prefix="/test", tags=["test-stack"])


def _require_test_stack() -> None:
    if os.getenv("SEED_TEST_DATA", "").strip().lower() not in ("1", "true", "yes"):
        raise HTTPException(status_code=403, detail="Not available.")


def _require_reset_key(x_test_stack_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("TEST_STACK_RESET_KEY", "").strip()
    if expected and x_test_stack_key != expected:
        raise HTTPException(status_code=403, detail="Invalid test stack key.")


@router.post("/jack-empty/reset")
async def reset_jack_empty(
    db: Session = Depends(get_db),
    _: None = Depends(_require_test_stack),
    __: None = Depends(_require_reset_key),
):
    try:
        log = reset_jack_empty_journey(db)
    except SeedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"reset_failed: {exc.__class__.__name__}") from exc
    return {"status": "ok", "log": log}


@router.get("/storage-probe")
async def storage_probe(_: None = Depends(_require_test_stack)):
    """Round-trip object storage without returning secrets."""
    import os as _os

    key = storage.save(b"leviii-probe", content_type="text/plain")
    ok = storage.exists(key)
    payload = storage.load(key) if ok else b""
    storage.delete(key)
    endpoint = _os.getenv("STORAGE_S3_ENDPOINT_URL", "").strip()
    bucket = _os.getenv("STORAGE_S3_BUCKET", "").strip()
    backend = _os.getenv("STORAGE_BACKEND", "local").lower()
    using_s3 = bool(bucket) and (backend == "s3" or _os.getenv("STORAGE_PREFER_S3", "").strip().lower() in ("1", "true", "yes"))
    return {
        "backend": "s3" if using_s3 else "local",
        "round_trip_ok": ok and payload == b"leviii-probe",
        "bucket_set": bool(bucket),
        "endpoint_host": urlparse(endpoint).hostname if endpoint else None,
    }


@router.post("/reorder-draft")
async def run_reorder_draft(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
    _: None = Depends(_require_test_stack),
):
    if current_user.staff_role not in (models.StaffRole.STOCKKEEPER, models.StaffRole.OWNER) and current_user.role not in (
        models.Role.ADMIN,
        models.Role.SUPERADMIN,
    ):
        raise HTTPException(status_code=403, detail="Store or owner only.")
    restaurant = get_or_create_restaurant(db, current_user)
    count = engine_triggers.maybe_draft_reorders(db, restaurant.id)
    db.commit()
    return {"drafted": count}