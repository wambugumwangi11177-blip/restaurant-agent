"""
app/kernel/rbac.py
──────────────────
One permission matrix for the whole OS. Routes ask for a *permission*, never a
role, so adding a role (or a department's permissions) is a one-place change.

Departments register their own permissions with `register_permissions` from
their package's __init__ — they never edit this file's core matrix.
"""

from __future__ import annotations

from app.kernel.models import Role

F, S, C, A = Role.FOUNDER, Role.STAFF, Role.CONTRACTOR, Role.ADVISOR

PERMISSIONS: dict[str, set[Role]] = {
    # Core records
    "records.read": {F, S, C, A},
    "records.write": {F, S, C},
    "records.delete": {F},
    # Company memory
    "memory.search": {F, S, C, A},
    "memory.ingest": {F, S},
    # Agents
    "agents.run": {F, S},
    "agents.read_runs": {F, S},
    # Approvals: seeing what's waiting vs. deciding it
    "approvals.read": {F, S},
    "approvals.propose": {F, S},
    "approvals.decide": {F},
    "autonomy.manage": {F},
    # Governance
    "audit.read": {F},
    "events.read": {F, S},
    "members.manage": {F},
    "privacy.manage": {F},
    "ops.read": {F},
    "feedback.write": {F, S},
}


def register_permissions(extra: dict[str, set[Role]]) -> None:
    clash = set(extra) & set(PERMISSIONS)
    if clash:
        raise ValueError(f"Permission names already registered: {sorted(clash)}")
    PERMISSIONS.update(extra)


def role_has(role: str, permission: str) -> bool:
    allowed = PERMISSIONS.get(permission)
    if allowed is None:
        # Unknown permission is a programming error: fail closed.
        return False
    try:
        return Role(role) in allowed
    except ValueError:
        return False


def permissions_for(role: str) -> list[str]:
    return sorted(p for p in PERMISSIONS if role_has(role, p))
