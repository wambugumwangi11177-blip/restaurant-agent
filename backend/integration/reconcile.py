"""Count + checksum reconciliation between the source system and the mirror.

Fail-closed rule: a run that cannot prove equality ends `mismatch` or
`errored`, never `clean`. A silently-partial mirror is worse than a loud one.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from integration.models import ReconcileRun


@dataclass(frozen=True)
class ReconcileResult:
    status: str          # clean | mismatch | errored
    source_count: int
    mirror_count: int
    detail: str


def checksum_ids(ids: list[str]) -> str:
    joined = "\n".join(sorted(ids))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def reconcile(
    db: Session,
    *,
    source_system_id: int,
    entity: str,
    source_ids: list[str],
    mirror_ids: list[str],
    tolerance: int = 0,
) -> ReconcileResult:
    missing = sorted(set(source_ids) - set(mirror_ids))
    extra = sorted(set(mirror_ids) - set(source_ids))
    drift = abs(len(source_ids) - len(mirror_ids))

    if drift > tolerance or missing or extra:
        detail = f"missing={len(missing)} extra={len(extra)} drift={drift}"
        status = "mismatch"
    else:
        detail = "counts and ids agree"
        status = "clean"

    db.add(
        ReconcileRun(
            source_system_id=source_system_id,
            entity=entity,
            source_count=len(source_ids),
            mirror_count=len(mirror_ids),
            source_checksum=checksum_ids(source_ids),
            mirror_checksum=checksum_ids(mirror_ids),
            status=status,
            detail={"missing": missing[:50], "extra": extra[:50], "detail": detail},
        )
    )
    db.commit()
    return ReconcileResult(status, len(source_ids), len(mirror_ids), detail)