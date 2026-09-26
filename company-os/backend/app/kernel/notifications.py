"""
app/kernel/notifications.py
───────────────────────────
In-app notifications for workspace members, plus the event subscribers that
create them. Notifying the company's own members is internal (no approval
needed); anything addressed to outsiders is an EXTERNAL tool instead.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kernel.events import subscribe
from app.kernel.models import Event, Membership, Notification, Role


def notify(db: Session, workspace_id: int, user_id: int, title: str, body: str = "", link: str | None = None) -> Notification:
    n = Notification(workspace_id=workspace_id, user_id=user_id, title=title[:300], body=body, link=link)
    db.add(n)
    db.flush()
    return n


def founders(db: Session, workspace_id: int) -> list[int]:
    return list(db.execute(
        select(Membership.user_id).where(Membership.workspace_id == workspace_id, Membership.role == Role.FOUNDER.value)
    ).scalars())


def _on_proposal_created(db: Session, event: Event) -> None:
    if event.payload.get("auto"):
        return
    for uid in founders(db, event.workspace_id):
        notify(db, event.workspace_id, uid, "Approval needed", event.payload.get("summary", ""),
               link=f"/approvals?focus={event.entity_id}")


def _on_proposal_failed(db: Session, event: Event) -> None:
    for uid in founders(db, event.workspace_id):
        notify(db, event.workspace_id, uid, "An approved action failed",
               f"{event.payload.get('tool_name')}: {event.payload.get('error')}",
               link=f"/approvals?focus={event.entity_id}")


def register_subscribers() -> None:
    subscribe("proposal.created", _on_proposal_created)
    subscribe("proposal.failed", _on_proposal_failed)
