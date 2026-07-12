"""
backend/ai/enterprise/audit_center.py
────────────────────────────────────────
Enterprise audit center (Phase 10). Rolls the per-restaurant governance trail
(AgentAuditLog) up to the organization level so a chain can answer "what did the
AI do across all our sites, and who approved it?" in one place.

Read-only aggregation over already-recorded audit data. No LLM.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

import models
from time_utils import utcnow


def _org_restaurant_ids(db: Session, organization_id: int) -> list[int]:
    return [
        r[0] for r in db.query(models.Restaurant.id)
        .filter(models.Restaurant.organization_id == organization_id)
        .all()
    ]


def org_audit_center(db: Session, organization_id: int, days: int = 30, limit: int = 100) -> dict:
    """Aggregated audit view for an organization: action counts, per-site
    activity, and the most recent entries across all sites."""
    org = db.query(models.Organization).filter(models.Organization.id == organization_id).first()
    if org is None:
        return {"available": False, "error": "Organization not found."}

    rids = _org_restaurant_ids(db, organization_id)
    if not rids:
        return {"available": True, "organization": org.name, "site_count": 0,
                "total_actions": 0, "by_action_type": {}, "by_site": {}, "recent": []}

    cutoff = utcnow() - timedelta(days=days)
    logs = (
        db.query(models.AgentAuditLog)
        .filter(
            models.AgentAuditLog.restaurant_id.in_(rids),
            models.AgentAuditLog.created_at >= cutoff,
        )
        .order_by(models.AgentAuditLog.created_at.desc())
        .all()
    )

    by_action: dict[str, int] = {}
    by_site: dict[int, int] = {}
    for e in logs:
        by_action[e.action_type] = by_action.get(e.action_type, 0) + 1
        by_site[e.restaurant_id] = by_site.get(e.restaurant_id, 0) + 1

    name_by_id = {
        r.id: r.name for r in db.query(models.Restaurant)
        .filter(models.Restaurant.id.in_(rids)).all()
    }

    return {
        "available": True,
        "organization": org.name,
        "site_count": len(rids),
        "window_days": days,
        "total_actions": len(logs),
        "by_action_type": by_action,
        "by_site": {name_by_id.get(rid, str(rid)): n for rid, n in by_site.items()},
        "recent": [
            {
                "site": name_by_id.get(e.restaurant_id, str(e.restaurant_id)),
                "action_type": e.action_type,
                "agent_name": e.agent_name,
                "reasoning": e.reasoning,
                "approved_by": e.approved_by,
                "created_at": e.created_at.isoformat(),
            }
            for e in logs[:limit]
        ],
    }
