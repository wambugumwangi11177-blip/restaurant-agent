"""
app/kernel/bootstrap.py
───────────────────────
Create a workspace and its first founder. Used by execution/bootstrap_workspace.py
(the only way the first account is created — there is no public sign-up) and by
the test suite, so both exercise the same code.
"""

from __future__ import annotations

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.kernel.audit import write_audit
from app.kernel.models import Membership, Role, User, Workspace
from app.kernel.schemas import normalize_phone
from app.security import hash_password, require_strong_password

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


class BootstrapError(ValueError):
    pass


def create_workspace_with_founder(
    db: Session,
    *,
    slug: str,
    name: str,
    email: str,
    full_name: str,
    password: str,
    phone: str | None = None,
    timezone: str = "Africa/Nairobi",
    currency: str = "KES",
) -> tuple[Workspace, User]:
    if not _SLUG.match(slug):
        raise BootstrapError("slug must be 2-63 chars of lowercase letters, digits and hyphens")
    if db.execute(select(Workspace).where(Workspace.slug == slug)).scalar_one_or_none():
        raise BootstrapError(f"workspace {slug!r} already exists")
    require_strong_password(password)
    email = email.strip().lower()
    user = db.execute(select(User).where(func.lower(User.email) == email)).scalar_one_or_none()
    if user is None:
        user = User(email=email, full_name=full_name, phone=normalize_phone(phone), password_hash=hash_password(password))
        db.add(user)
    ws = Workspace(slug=slug, name=name, timezone=timezone, currency=currency.upper())
    db.add(ws)
    db.flush()
    db.add(Membership(workspace_id=ws.id, user_id=user.id, role=Role.FOUNDER.value))
    write_audit(db, action="workspace.create", workspace_id=ws.id, entity_type="workspace", entity_id=ws.id,
                changes={"slug": slug, "founder_user_id": user.id}, actor_user_id=user.id)
    db.flush()
    return ws, user
