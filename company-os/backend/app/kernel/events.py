"""
app/kernel/events.py
────────────────────
Event bus. `emit` persists an Event row (in the caller's transaction) and then
runs in-process subscribers against the same session.

Rule carried over from restaurant-agent directive 019: never emit a dead event.
Every type in EVENT_TYPES is (a) shown in the activity feed (GET /events) and
(b) listed with the consumer that acts on it. `emit` rejects unregistered types,
so a typo can't create an event nobody reads.

Subscriber failures are logged and swallowed: a failed notification must never
roll back the business write that caused it.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.kernel.models import Event

logger = logging.getLogger("kernel.events")

# type -> who consumes it (documentation that is enforced to exist)
EVENT_TYPES: dict[str, str] = {
    "record.created": "activity feed",
    "record.updated": "activity feed",
    "record.deleted": "activity feed",
    "link.created": "activity feed",
    "document.ingested": "activity feed",
    "member.added": "activity feed",
    "person.erased": "activity feed; privacy register",
    "proposal.created": "activity feed; founder notification (approval inbox)",
    "proposal.approved": "activity feed",
    "proposal.rejected": "activity feed",
    "proposal.executed": "activity feed",
    "proposal.failed": "activity feed; founder notification",
}

Handler = Callable[[Session, Event], None]
_handlers: dict[str, list[Handler]] = defaultdict(list)


class UnknownEventType(ValueError):
    pass


def register_event_types(extra: dict[str, str]) -> None:
    """Departments add their own event types here (never by editing EVENT_TYPES)."""
    clash = set(extra) & set(EVENT_TYPES)
    if clash:
        raise ValueError(f"Event types already registered: {sorted(clash)}")
    EVENT_TYPES.update(extra)


def subscribe(event_type: str, handler: Handler) -> None:
    if event_type not in EVENT_TYPES:
        raise UnknownEventType(event_type)
    if handler not in _handlers[event_type]:  # idempotent: no duplicate fan-out
        _handlers[event_type].append(handler)


def clear_handlers() -> None:
    _handlers.clear()


def emit(
    db: Session,
    event_type: str,
    *,
    workspace_id: int,
    entity_type: str | None = None,
    entity_id: int | None = None,
    payload: dict[str, Any] | None = None,
    actor_user_id: int | None = None,
    actor_agent_run_id: int | None = None,
) -> Event:
    if event_type not in EVENT_TYPES:
        raise UnknownEventType(event_type)
    event = Event(
        workspace_id=workspace_id,
        type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
        actor_user_id=actor_user_id,
        actor_agent_run_id=actor_agent_run_id,
    )
    db.add(event)
    db.flush()
    for handler in list(_handlers.get(event_type, [])):
        try:
            with db.begin_nested():
                handler(db, event)
        except Exception:  # noqa: BLE001 — see module docstring
            logger.exception("event handler %s failed for %s", getattr(handler, "__name__", handler), event_type)
    return event
