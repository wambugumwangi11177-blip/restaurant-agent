"""
backend/owner/mpesa_statement.py — taking an uploaded M-Pesa statement in (docs/v2/SPEC.md §4, sprint S6.1).

One function, used by the upload endpoint (routers/owner_mpesa.py) and by the demo restaurant, so a statement is read, de-duplicated
and stored the same way wherever it comes from. The parser (parsers/mpesa_csv.py) decides what the file says; this decides what is new.

A payment already on file (M-Pesa's receipt number, per restaurant) is not added again, so uploading the same file twice, or two
statements whose periods overlap, is safe. A file that brings nothing new stores nothing: there is no empty upload to undo.
"""
from __future__ import annotations

import os
import re

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
from parsers.mpesa_csv import DEFAULT_FORMAT, StatementError, parse_statement
from owner.states import iso

NOT_READ_SHOWN = 25                       # how many unread rows the owner is shown; the count says how many there are
_CHUNK = 400                              # receipts per IN (...) query: well under SQLite's variable limit


def clean_filename(name: str | None) -> str:
    base = os.path.basename((name or "").replace("\\", "/"))
    return re.sub(r"[\x00-\x1f\x7f]", "", base).strip()[:255] or "statement.csv"


def _already_on_file(db: Session, restaurant_id: int, receipts: list[str]) -> set[str]:
    found: set[str] = set()
    for i in range(0, len(receipts), _CHUNK):
        chunk = receipts[i:i + _CHUNK]
        found.update(r for (r,) in db.query(models.MpesaStatementLine.receipt).filter(
            models.MpesaStatementLine.restaurant_id == restaurant_id, models.MpesaStatementLine.receipt.in_(chunk)))
    return found


def upload_json(upload: models.MpesaStatementUpload) -> dict:
    return {"id": upload.id, "filename": upload.filename, "uploaded_at": iso(upload.uploaded_at), "lines": upload.line_count,
            "from": iso(upload.period_start), "to": iso(upload.period_end),
            "uploaded_by": upload.uploaded_by.email if upload.uploaded_by else None}


def import_statement(db: Session, restaurant_id: int, user_id: int | None, filename: str | None, raw: bytes,
                     fmt: str = DEFAULT_FORMAT, *, commit: bool = True) -> dict:
    """Read `raw` and store what is new. Raises StatementError (a message for the owner) when the file cannot be read as a statement.
    `commit=False` flushes instead, for a caller that commits a larger piece of work itself (the demo restaurant)."""
    parsed = parse_statement(raw, fmt)
    on_file = _already_on_file(db, restaurant_id, [line.receipt for line in parsed.lines])
    fresh = [line for line in parsed.lines if line.receipt not in on_file]
    upload = None
    if fresh:
        times = [line.completed_at for line in fresh]
        upload = models.MpesaStatementUpload(restaurant_id=restaurant_id, filename=clean_filename(filename), parser=parsed.parser,
                                             uploaded_by_user_id=user_id, line_count=len(fresh), period_start=min(times), period_end=max(times))
        db.add(upload)
        db.flush()
        db.add_all(models.MpesaStatementLine(
            restaurant_id=restaurant_id, upload_id=upload.id, receipt=line.receipt, completed_at=line.completed_at,
            paid_in_cents=line.paid_in_cents, withdrawn_cents=line.withdrawn_cents, details=line.details, status=line.status,
            balance_cents=line.balance_cents) for line in fresh)
        try:
            db.commit() if commit else db.flush()
        except IntegrityError:
            db.rollback()
            raise StatementError("Some of these payments were uploaded at the very same moment. Upload the file again.") from None
        db.refresh(upload)
    return {
        "upload": upload_json(upload) if upload else None,
        "new": len(fresh),
        "already_uploaded": len(parsed.lines) - len(fresh),
        "not_read": [{"row": s.row, "reason": s.reason} for s in parsed.skipped[:NOT_READ_SHOWN]],
        "not_read_count": len(parsed.skipped),
        "money_in_kes": sum(line.paid_in_cents for line in fresh) / 100,
        "money_out_kes": sum(line.withdrawn_cents for line in fresh) / 100,
        "about": parsed.about,
    }
