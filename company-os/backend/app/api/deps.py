"""
app/api/deps.py
───────────────
Request authentication and permission checks.

A bearer token carries (user id, workspace id, token_version). It is accepted
only if the user is active, the version still matches (logout-all / password
change / removal bump it), and the user is still a member of that workspace —
membership and role are re-read on every request, so demoting or removing a
member takes effect immediately, not at token expiry.
"""

from __future__ import annotations

from collections.abc import Callable

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.kernel.models import Membership, User
from app.kernel.rbac import role_has
from app.kernel.tenancy import Principal
from app.security import decode_access_token

_UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"}
)


def get_principal(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _UNAUTHORIZED
    try:
        claims = decode_access_token(authorization[7:].strip())
        user_id, workspace_id, version = int(claims["sub"]), int(claims["wid"]), int(claims["ver"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise _UNAUTHORIZED from None
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.token_version != version:
        raise _UNAUTHORIZED
    membership = db.execute(
        select(Membership).where(Membership.user_id == user_id, Membership.workspace_id == workspace_id)
    ).scalar_one_or_none()
    if membership is None:
        raise _UNAUTHORIZED
    return Principal(user_id=user_id, workspace_id=workspace_id, role=membership.role, user=user)


def require(permission: str) -> Callable[..., Principal]:
    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if not role_has(principal.role, permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your role ({principal.role}) lacks '{permission}'")
        return principal

    return dependency
