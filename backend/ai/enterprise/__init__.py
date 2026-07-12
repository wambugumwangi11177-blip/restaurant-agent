"""
backend/ai/enterprise/
─────────────────────────
Enterprise administration (Phase 10) for chains/franchises: cross-location
benchmarking and an organization-wide audit center over the existing
per-restaurant analytics and governance trail. Deterministic, read-only.

Deliberately NOT included here: cross-account support impersonation. Issuing a
token to act as another user is a privilege-escalation surface that must be
designed with a security review (scoped, time-boxed, fully audited, revocable) —
it is left as a documented follow-up rather than auto-built, per this project's
security posture.
"""

from .benchmarking import benchmark_organization  # noqa: F401
from .audit_center import org_audit_center  # noqa: F401
