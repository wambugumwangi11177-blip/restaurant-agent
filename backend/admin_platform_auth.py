"""Company OS / super-admin access to platform routes (not used by the Eleven UI)."""
from __future__ import annotations

import os
import secrets

import jwt
from jwt.exceptions import PyJWTError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

import auth
import models
from database import get_db


def _service_token_ok(request: Request) -> bool:
    expected = os.getenv("COMPANY_OS_SERVICE_TOKEN", "").strip()
    if not expected:
        return False
    provided = (request.headers.get("X-Company-OS-Token") or "").strip()
    return bool(provided and secrets.compare_digest(provided, expected))


def _service_actor(db: Session) -> models.User:
    email = (os.getenv("COMPANY_OS_ACTOR_EMAIL") or "wambugu@leviii.ai").strip().lower()
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=503,
            detail="Company OS service actor is not configured on this stack.",
        )
    return user


def _bearer_superadmin(request: Request, db: Session) -> models.User | None:
    header = request.headers.get("Authorization") or ""
    if not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        email = payload.get("sub")
        if not email:
            return None
    except PyJWTError:
        return None
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None or not user.is_active:
        return None
    if payload.get("ver", 0) != (user.token_version or 0):
        return None
    if user.role != models.Role.SUPERADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super-admin only.")
    return user


async def require_platform_admin(
    request: Request,
    db: Session = Depends(get_db),
) -> models.User:
    """`Authorization: Bearer` (SUPERADMIN) or `X-Company-OS-Token` (service)."""
    if _service_token_ok(request):
        return _service_actor(db)
    user = _bearer_superadmin(request, db)
    if user:
        return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Platform admin credentials required.",
        headers={"WWW-Authenticate": "Bearer"},
    )