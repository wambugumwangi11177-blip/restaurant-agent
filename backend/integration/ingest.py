"""Idempotent mirror ingest.

Contract: applying the same source payload twice must produce exactly one
mirror row and two MirrorEvent rows (one `inserted`, one `skipped`). That is
what makes a re-run after a crash safe.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from integration.models import MirrorEvent


def payload_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def latest_version(db: Session, source_system_id: int, entity: str, source_id: str) -> str | None:
    row = (
        db.query(MirrorEvent)
        .filter(
            MirrorEvent.source_system_id == source_system_id,
            MirrorEvent.entity == entity,
            MirrorEvent.source_id == source_id,
            MirrorEvent.action.in_(("inserted", "superseded")),
        )
        .order_by(MirrorEvent.id.desc())
        .first()
    )
    if row is None:
        return None
    return row.source_version


def ingest(
    db: Session,
    *,
    source_system_id: int,
    entity: str,
    source_id: str,
    source_version: str,
    payload: dict[str, Any],
    commit: bool = True,
) -> str:
    """Return the action taken: inserted | superseded | skipped.

    `commit=False` lets a caller ingest a whole batch inside one transaction:
    the row is flushed (so the very next latest_version() in the same batch can
    see it) but not committed, and the caller commits once at the end. COMMIT
    is the expensive part — one fsync per record turns a 500-record push into
    hundreds of round trips, which is how a batch ingest hits the gunicorn
    timeout. The flush is NOT optional: SessionLocal is autoflush=False, so
    without it a record repeated inside a single batch would not be seen by the
    dedupe check and would insert twice.
    """
    current = latest_version(db, source_system_id, entity, source_id)
    if current == source_version:
        action = "skipped"
        reason = "same source_version already applied"
    elif current is None:
        action = "inserted"
        reason = None
    else:
        action = "superseded"
        reason = f"replaced {current}"

    db.add(
        MirrorEvent(
            source_system_id=source_system_id,
            entity=entity,
            source_id=source_id,
            source_version=source_version,
            payload_sha256=payload_sha256(payload),
            action=action,
            reason=reason,
            raw=payload,
        )
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return action
