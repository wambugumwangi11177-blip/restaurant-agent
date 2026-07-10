"""
backend/ai/whatsapp/optout.py
──────────────────────────────
Customer marketing/communications opt-out (suppression list). Pure DB helpers,
no Twilio. Used by the inbound webhook (to RECORD a STOP) and the outbound send
engine + winback selection (to HONOUR it).

Phones are matched on their normalized form (payments.mpesa_client.normalize_phone,
canonical 2547XXXXXXXX) so a STOP arriving as "whatsapp:+254712345678" suppresses
an order stored as "0712345678". If a number can't be normalized we fall back to a
digits-only comparison rather than silently failing to match.

STOP keywords follow the Twilio/industry-standard set; START/UNSTOP resume.
"""

from sqlalchemy.orm import Session
import models
from payments.mpesa_client import normalize_phone

# Standard opt-out / opt-in keywords (compared case-insensitively, trimmed).
STOP_KEYWORDS = {"stop", "stopall", "unsubscribe", "cancel", "end", "quit", "optout", "opt out"}
START_KEYWORDS = {"start", "unstop", "subscribe", "optin", "opt in"}


def canonical(phone: str) -> str:
    """Best-effort canonical key for matching. Falls back to digits-only."""
    if not phone:
        return ""
    normalized = normalize_phone(phone)
    if normalized:
        return normalized
    return "".join(ch for ch in phone if ch.isdigit())


def last9(phone: str) -> str:
    """
    Last 9 digits of a phone — the subscriber part of a Kenyan mobile number,
    identical whether stored as 0712345678, +254712345678 or 254712345678.
    Used for a SQL `LIKE %suffix%` pre-filter so customer lookups don't depend on
    a capped recent-order scan; callers still confirm with canonical() to rule out
    the rare suffix collision.
    """
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return digits[-9:] if len(digits) >= 9 else ""


def is_stop_keyword(message: str) -> bool:
    return message.strip().lower() in STOP_KEYWORDS


def is_start_keyword(message: str) -> bool:
    return message.strip().lower() in START_KEYWORDS


def is_opted_out(db: Session, phone: str) -> bool:
    key = canonical(phone)
    if not key:
        return False
    return db.query(models.CustomerOptOut).filter(
        models.CustomerOptOut.customer_phone == key
    ).first() is not None


def record_opt_out(db: Session, phone: str, source: str = "whatsapp_stop") -> bool:
    """Idempotent. Returns True if a new opt-out was written, False if already present."""
    key = canonical(phone)
    if not key:
        return False
    if is_opted_out(db, phone):
        return False
    db.add(models.CustomerOptOut(customer_phone=key, source=source))
    db.commit()
    return True


def remove_opt_out(db: Session, phone: str) -> bool:
    """Resume messaging (customer sent START). Returns True if a row was removed."""
    key = canonical(phone)
    if not key:
        return False
    row = db.query(models.CustomerOptOut).filter(
        models.CustomerOptOut.customer_phone == key
    ).first()
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True
