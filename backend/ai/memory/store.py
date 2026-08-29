"""
backend/ai/memory/store.py
───────────────────────────
Structured long-term memory for all agents (Layer 2).

Design philosophy:
  - Memory is stored in PostgreSQL. No vector DB needed at this scale.
  - Retrieval is by month + event_type — fast indexed queries.
  - The interface is abstract enough that a vector DB can replace
    the storage layer later without changing agent code.
  - Agents write memories automatically. Owners can annotate them.

Two types of memory:

1. AUTO-GENERATED: The system creates memory events from observed data
   - Large revenue spikes (>50% above average) → MemoryEvent(impact_type="traffic_spike")
   - Stockouts → MemoryEvent(impact_type="stockout", affected_items=[...])
   - Approved price changes → MemoryEvent(impact_type="price_change")

2. HUMAN-ANNOTATED: Owner can add context
   - "That spike was because of the Safaricom Golf Tournament next door"
   - "We ran out of chicken because the supplier didn't deliver"

The orchestrator calls recall_context() before making decisions.
"""

import json
import logging
from datetime import date, timedelta
from sqlalchemy.orm import Session
import models
from time_utils import utcnow

logger = logging.getLogger("ai.memory")


# ─────────────────────────────────────────────────────────────────────────────
# WRITE — create memory events
# ─────────────────────────────────────────────────────────────────────────────

def remember(
    db: Session,
    restaurant_id: int,
    event_type: str,
    event_name: str,
    event_date: date,
    impact_type: str,
    revenue_delta_pct: float | None = None,
    traffic_delta_pct: float | None = None,
    affected_items: list | None = None,
    agent_notes: str = "",
    created_by: str = "system",
) -> int:
    """
    Create a new memory event.
    Returns the MemoryEvent.id.
    """
    mem = models.MemoryEvent(
        restaurant_id      = restaurant_id,
        event_type         = event_type,
        event_name         = event_name,
        event_date         = event_date,
        month_number       = event_date.month,
        day_of_week        = event_date.weekday(),
        impact_type        = impact_type,
        revenue_delta_pct  = revenue_delta_pct,
        traffic_delta_pct  = traffic_delta_pct,
        affected_items     = json.dumps(affected_items or []),
        agent_notes        = agent_notes,
        created_by         = created_by,
    )
    db.add(mem)
    db.commit()
    db.refresh(mem)
    logger.info(f"[Memory] Stored: {event_name} ({impact_type}) for restaurant {restaurant_id}")
    return mem.id


def annotate(
    db: Session,
    memory_id: int,
    restaurant_id: int,
    human_notes: str,
    user_email: str,
) -> dict:
    """Owner adds context to a memory event."""
    mem = db.query(models.MemoryEvent).filter(
        models.MemoryEvent.id == memory_id,
        models.MemoryEvent.restaurant_id == restaurant_id,
    ).first()
    if not mem:
        return {"error": "Memory event not found"}
    mem.human_notes = human_notes
    db.commit()
    return {"success": True, "memory_id": memory_id}


# ─────────────────────────────────────────────────────────────────────────────
# READ — retrieve relevant memories
# ─────────────────────────────────────────────────────────────────────────────

def recall_context(
    db: Session,
    restaurant_id: int,
    for_date: date,
    lookback_years: int = 2,
) -> dict:
    """
    Retrieve memories relevant to a given date.
    Returns memories for the same month in prior years + same week + stockouts.

    Called by: orchestrator before making decisions about a specific date.
    """
    same_month = for_date.month
    same_dow   = for_date.weekday()

    # Same month in prior years — seasonal pattern retrieval
    seasonal_memories = db.query(models.MemoryEvent).filter(
        models.MemoryEvent.restaurant_id == restaurant_id,
        models.MemoryEvent.month_number  == same_month,
        models.MemoryEvent.event_date    < for_date,
    ).order_by(models.MemoryEvent.event_date.desc()).limit(10).all()

    # Recent stockouts (last 90 days) — supply chain awareness
    cutoff = for_date - timedelta(days=90)
    recent_stockouts = db.query(models.MemoryEvent).filter(
        models.MemoryEvent.restaurant_id == restaurant_id,
        models.MemoryEvent.impact_type   == "stockout",
        models.MemoryEvent.event_date    >= cutoff,
    ).order_by(models.MemoryEvent.event_date.desc()).limit(5).all()

    # High-impact events (>30% revenue delta) — regardless of date
    high_impact = db.query(models.MemoryEvent).filter(
        models.MemoryEvent.restaurant_id == restaurant_id,
        models.MemoryEvent.revenue_delta_pct >= 30,
    ).order_by(models.MemoryEvent.event_date.desc()).limit(5).all()

    def _serialize(m: models.MemoryEvent) -> dict:
        return {
            "id":               m.id,
            "event_name":       m.event_name,
            "event_type":       m.event_type,
            "event_date":       m.event_date.isoformat(),
            "impact_type":      m.impact_type,
            "revenue_delta_pct": m.revenue_delta_pct,
            "affected_items":   json.loads(m.affected_items or "[]"),
            "agent_notes":      m.agent_notes,
            "human_notes":      m.human_notes,
        }

    return {
        "seasonal_memories": [_serialize(m) for m in seasonal_memories],
        "recent_stockouts":  [_serialize(m) for m in recent_stockouts],
        "high_impact_events": [_serialize(m) for m in high_impact],
        "context_summary":   _build_context_summary(seasonal_memories, recent_stockouts),
        "for_date":          for_date.isoformat(),
        "for_month":         for_date.strftime("%B"),
    }


def _build_context_summary(seasonal: list, stockouts: list) -> str:
    """
    Build a plain-English context string for the orchestrator's reasoning.
    Example: "June historically shows +45% revenue (Madaraka Day spike in 2023).
              Chicken ran out 3 times in the last 90 days."
    """
    parts = []
    if seasonal:
        top = max(seasonal, key=lambda m: abs(m.revenue_delta_pct or 0), default=None)
        if top and top.revenue_delta_pct:
            direction = "above" if top.revenue_delta_pct > 0 else "below"
            parts.append(
                f"{top.event_date.strftime('%B')} historically shows "
                f"{abs(top.revenue_delta_pct):.0f}% {direction} average revenue "
                f"(from {top.event_name} on {top.event_date.isoformat()})."
            )
    if stockouts:
        items = set()
        for m in stockouts:
            for item in json.loads(m.affected_items or "[]"):
                items.add(item)
        if items:
            parts.append(f"Recent stockouts: {', '.join(list(items)[:3])}.")

    return " ".join(parts) if parts else "No significant historical patterns for this period."


def recall_recent_reflections(db: Session, restaurant_id: int, limit: int = 3) -> list[dict]:
    """
    The strategist's own prior conclusions, most recent first — not seasonal
    or date-keyed like recall_context(), just "what did I last tell this
    owner." Lets a new run see its own history instead of starting cold.
    """
    rows = (
        db.query(models.MemoryEvent)
        .filter(
            models.MemoryEvent.restaurant_id == restaurant_id,
            models.MemoryEvent.event_type == "strategy_reflection",
        )
        .order_by(models.MemoryEvent.event_date.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "event_date": m.event_date.isoformat(),
            "event_name": m.event_name,
            "agent_notes": m.agent_notes,
        }
        for m in rows
    ]


def record_strategy_reflection(db: Session, restaurant_id: int, goal: str, strategy: dict) -> int:
    """
    Persist what the strategist just concluded so the next run — on-demand or
    scheduled — can recall it via recall_recent_reflections() instead of
    reasoning from scratch every time.
    """
    headline = (strategy.get("headline") or "").strip()
    steps = [s.get("action", "") for s in strategy.get("steps", [])[:3] if isinstance(s, dict)]
    risks = strategy.get("risks", [])[:2]
    notes = headline
    if steps:
        notes += " | Steps: " + "; ".join(steps)
    if risks:
        notes += " | Risks: " + "; ".join(risks)

    return remember(
        db, restaurant_id,
        event_type  = "strategy_reflection",
        event_name  = f"Strategy: {headline[:80] or goal[:80]}",
        event_date  = utcnow().date(),
        impact_type = "strategy_outcome",
        agent_notes = notes[:2000],
        created_by  = "strategist",
    )


def auto_record_revenue_spike(
    db: Session,
    restaurant_id: int,
    event_date: date,
    delta_pct: float,
) -> None:
    """
    Auto-called by the revenue forecaster when an anomaly is detected.
    Only records if delta is significant enough to be worth remembering.
    """
    if abs(delta_pct) < 30:
        return   # Not significant enough to store

    impact = "traffic_spike" if delta_pct > 0 else "traffic_drop"
    name   = f"{'Revenue spike' if delta_pct > 0 else 'Revenue drop'} on {event_date.isoformat()}"

    # Don't duplicate — check if already recorded for this date
    existing = db.query(models.MemoryEvent).filter(
        models.MemoryEvent.restaurant_id == restaurant_id,
        models.MemoryEvent.event_date    == event_date,
        models.MemoryEvent.impact_type   == impact,
    ).first()
    if existing:
        return

    remember(
        db, restaurant_id,
        event_type        = "anomaly",
        event_name        = name,
        event_date        = event_date,
        impact_type       = impact,
        revenue_delta_pct = delta_pct,
        agent_notes       = f"Auto-detected: revenue was {abs(delta_pct):.0f}% {'above' if delta_pct > 0 else 'below'} average.",
    )


def auto_record_stockout(
    db: Session,
    restaurant_id: int,
    item_name: str,
    event_date: date | None = None,
) -> None:
    """Auto-called when stock level hits 0."""
    if event_date is None:
        event_date = utcnow().date()

    remember(
        db, restaurant_id,
        event_type     = "stockout",
        event_name     = f"{item_name} stockout",
        event_date     = event_date,
        impact_type    = "stockout",
        affected_items = [item_name],
        agent_notes    = f"{item_name} reached zero stock on {event_date.isoformat()}.",
    )
