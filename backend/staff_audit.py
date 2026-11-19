"""Append-only staff entry records. Callers commit."""
import json

import models
from time_utils import utcnow


def record_entry(
    db,
    restaurant_id: int,
    user: models.User,
    action: str,
    entity_type: str,
    summary: str,
    entity_id: int | None = None,
    detail: dict | None = None,
) -> models.StaffEntryAudit:
    row = models.StaffEntryAudit(
        restaurant_id=restaurant_id,
        user_id=user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        detail_json=json.dumps(detail or {}, sort_keys=True),
        created_at=utcnow(),
    )
    db.add(row)
    return row
