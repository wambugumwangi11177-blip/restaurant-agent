"""
app/kernel/audit.py
───────────────────
Append-only audit trail. Every write path calls `write_audit` in the same
transaction as the change it records, so a change without an audit row cannot
commit.

PII never enters the audit log: for fields listed in PII_FIELDS the diff records
only that the field changed, not its values. That is what lets the audit log be
immutable (DB trigger, migration 0001) *and* the OS honour right-to-erasure
requests under Kenya's Data Protection Act — erasing a person never requires
rewriting history.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.kernel.models import AuditLog
from app.logging_config import request_id_var

PII_FIELDS: dict[str, set[str]] = {
    "person": {"full_name", "email", "phone", "notes"},
    "user": {"email", "full_name", "phone"},
    "channel_message": {"from_addr", "to_addr", "body"},
}
# Never recorded at all, not even as "changed".
SECRET_FIELDS = {"password_hash", "mfa_secret"}
IGNORED_FIELDS = {"updated_at", "created_at", "tsv"}


def _jsonable(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return v


def snapshot(obj: Any) -> dict[str, Any]:
    """Column values of an ORM object as a plain dict."""
    return {c.key: getattr(obj, c.key) for c in obj.__mapper__.column_attrs}


def diff(entity_type: str, before: dict[str, Any] | None, after: dict[str, Any] | None) -> dict[str, Any]:
    before, after = before or {}, after or {}
    pii = PII_FIELDS.get(entity_type, set())
    out: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if key in SECRET_FIELDS or key in IGNORED_FIELDS:
            continue
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        if key in pii:
            out[key] = {"changed": True}
        else:
            out[key] = {"from": _jsonable(old), "to": _jsonable(new)}
    return out


def write_audit(
    db: Session,
    *,
    action: str,
    workspace_id: int | None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    changes: dict[str, Any] | None = None,
    actor_user_id: int | None = None,
    actor_agent_run_id: int | None = None,
) -> AuditLog:
    row = AuditLog(
        workspace_id=workspace_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes or {},
        actor_user_id=actor_user_id,
        actor_agent_run_id=actor_agent_run_id,
        request_id=request_id_var.get() if request_id_var.get() != "-" else None,
    )
    db.add(row)
    return row
