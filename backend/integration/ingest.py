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
        )
        .order_by(MirrorEvent.id.desc())
        .first()
    )
    if row is None or row.action not in ("inserted", "superseded"):
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
) -> str:
    """Return the action taken: inserted | superseded | skipped."""
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
    db.commit()
    return action
