"""
backend/audit.py
─────────────────
Recording sensitive actions taken by humans.

The gap this closes: routers/auth.py and routers/export.py contained ZERO logger
calls between them. Login success and failure, account lockout, MFA enable and
disable, session revocation, bulk export of every customer's name and phone, and
irreversible PII erasure all happened without leaving a trace anywhere. The
existing AgentAuditLog covers what the AI did, and covers it well — but it has
no room for a human actor, and its non-null restaurant_id/agent_name columns
cannot represent a failed login for an email that has no account.

Two design decisions worth stating, because both are easy to get wrong:

1. THE AUDIT ROW SHARES THE CALLER'S TRANSACTION.
   `record_security_event` calls db.add() and does NOT commit. The row lands
   when the operation it describes lands, so a rolled-back operation cannot
   leave a row claiming it happened, and an audit write that fails takes the
   operation down with it rather than letting it proceed unrecorded. This is
   the opposite of tracker.write_audit_log, which commits independently and
   swallows failures — fine for a best-effort AI governance note, not fine for
   the record of who exported your customer list.

   The caller commits. For read-only endpoints that would not otherwise commit
   (the CSV exports), `commit=True` is available and does the commit itself.

2. THE TRAIL MUST NOT BECOME ITS OWN PII LEAK.
   Identifiers are stored as a keyed HMAC, never raw. Writing the raw phone
   number would mean the erasure endpoint permanently records the number the
   customer asked to have forgotten — the compliance control creating the
   compliance breach. A keyed hash still supports the questions an investigator
   asks ("was this same target hit repeatedly?", "does this match the number in
   the complaint?", by hashing the candidate) without retaining the value.

   The key is SECRET_KEY, so the hashes are not reversible by dictionary attack
   over the small space of Kenyan phone numbers the way a bare SHA-256 would be.
"""

import hashlib
import hmac
import json
import logging
import os

from sqlalchemy.orm import Session

import models
from logging_config import request_id_var
from observability import degraded

logger = logging.getLogger("security.audit")

# Outcomes. Kept as plain strings (matching action_type on AgentAuditLog) rather
# than an enum, so adding one never needs a migration.
SUCCESS = "success"
FAILURE = "failure"
DENIED = "denied"


def _canonical(value: str) -> str:
    """
    Reduce an identifier to one canonical form before hashing.

    This is load-bearing, not cosmetic. There are TWO normalize_phone functions
    in this codebase and they disagree: phone_utils.normalize_phone returns
    "+254712345678" (used on the auth/owner-phone path) while
    payments.mpesa_client.normalize_phone returns "254712345678" (used on the
    export/erasure path). Hashing the caller's string directly would give the
    same customer two different target_refs depending on which endpoint recorded
    the event — which silently destroys the one thing target_ref exists for,
    namely correlating actions on the same target across the system.

    Stripping the leading "+" and casing collapses both forms onto one value.
    """
    return str(value).strip().lstrip("+").lower()


def hash_identifier(value: str | None) -> str | None:
    """
    Keyed, non-reversible reference to an identifier (phone, email) for
    `target_ref`. Returns None for empty input.

    HMAC-SHA256 keyed with SECRET_KEY, truncated to 32 hex chars — long enough
    that collisions are not a practical concern for an audit trail, short enough
    to read in a query result. Truncation does not weaken the pre-image
    resistance that matters here.

    To check whether a row refers to a known number, hash the candidate and
    compare — do not try to reverse the stored value.
    """
    if not value:
        return None
    key = (os.getenv("SECRET_KEY") or "").encode("utf-8")
    return hmac.new(key, _canonical(value).encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def _client_ip(request) -> str | None:
    """Real client IP, reusing the spoof-resistant X-Forwarded-For handling the
    rate limiter already implements (see rate_limit._client_ip for why reading
    the leftmost value is wrong). Never fails the caller."""
    if request is None:
        return None
    try:
        from rate_limit import _client_ip as resolve
        return resolve(request)
    except Exception:
        return None


def record_security_event(
    db: Session,
    request,
    event_type: str,
    outcome: str = SUCCESS,
    *,
    actor: "models.User | None" = None,
    actor_email: str | None = None,
    tenant_id: int | None = None,
    restaurant_id: int | None = None,
    target_type: str | None = None,
    target_ref: str | None = None,
    commit: bool = False,
    **detail,
) -> None:
    """
    Record one sensitive action.

    Adds the row to `db` WITHOUT committing (see module docstring) unless
    `commit=True`, which read-only endpoints use since they have no write of
    their own to ride along with.

    `target_ref` must already be hashed by the caller via hash_identifier() —
    it is not hashed here, because some targets (a user id, a restaurant id) are
    not PII and are more useful stored plainly.

    `detail` is JSON-serialised into the detail column. Pass counts and
    metadata, never PII.

    Always emits a structured log line as well, so the trail still exists in the
    log aggregator if the database write is rolled back with the transaction.
    """
    actor_email = actor_email or (actor.email if actor is not None else None)
    if actor is not None:
        tenant_id = tenant_id if tenant_id is not None else actor.tenant_id

    request_id = request_id_var.get()
    source_ip = _client_ip(request)

    # Log first and unconditionally: this survives a transaction rollback, and a
    # DB that is refusing writes is exactly when you most want the record.
    logger.info(
        "security_event %s outcome=%s actor=%s",
        event_type, outcome, actor_email or "-",
        extra={
            "event_type": event_type,
            "outcome": outcome,
            "actor_email": actor_email,
            "actor_user_id": getattr(actor, "id", None),
            "restaurant_id": restaurant_id,
            "target_type": target_type,
            "target_ref": target_ref,
            "source_ip": source_ip,
            **detail,
        },
    )

    try:
        row = models.SecurityAuditLog(
            event_type    = event_type,
            outcome       = outcome,
            actor_user_id = getattr(actor, "id", None),
            actor_email   = actor_email,
            tenant_id     = tenant_id,
            restaurant_id = restaurant_id,
            target_type   = target_type,
            target_ref    = target_ref,
            source_ip     = source_ip,
            request_id    = request_id if request_id != "-" else None,
            detail        = json.dumps(detail or {}, default=str),
        )
        db.add(row)
        if commit:
            db.commit()
    except Exception as exc:
        # A failure here is serious — but the log line above already went out,
        # so the event is not lost, and raising would turn "we couldn't write
        # the audit row" into "the user's login broke".
        if commit:
            try:
                db.rollback()
            except Exception:  # pragma: no cover
                pass
        degraded("audit.security_audit_log", exc, event_type=event_type)
