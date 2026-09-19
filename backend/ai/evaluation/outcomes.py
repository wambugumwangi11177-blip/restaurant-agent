"""Did the owner's decision actually work?

The loop this system runs is: an event happens, a detector notices, the system
recommends, the owner decides, the system measures. Stage five had no input.
`AttentionDecision` recorded the click and was read in exactly one place — to
hide the card from the next feed. `run_feedback_cycle` measured forecasts, not
decisions. So the system learned whether its revenue prediction was right, and
nothing at all about whether its recommendations were worth taking.

ai/orchestrator/executive.py:on_recommendation_approved says in its docstring
that "at day 7 and day 14, the evaluation agent checks if revenue from that
item improved" and its body writes a memory entry and an audit log. Nothing
was scheduled, nothing was measured. This is that half, built on the machinery
that already exists for forecasts: record_prediction before the fact,
evaluate_prediction after, get_agent_accuracy and agent_reliability on top —
which feed straight back into decision ranking through
ai/decisions/__init__.py::_apply_reliability. An agent whose advice does not
pay off is trusted less next time, which is the whole point of measuring.

WHAT IS MEASURABLE, AND WHAT IS NOT
Only a decision whose claimed impact attaches to something countable can be
scored. A price change on a menu item is countable: the item's gross profit
over the 30 days before the change against the 30 days after. "Check the beef
usage against the recipes" is not — the outcome happens in a store room and
leaves no row. Unmeasurable decisions are still recorded, but as advice given,
never scored, because an unscoreable decision counted as a miss would punish
an agent for the shape of its advice rather than its quality.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from time_utils import utcnow
from .tracker import record_prediction, evaluate_prediction

logger = logging.getLogger("ai.outcomes")

DECISION_IMPACT = "decision_impact"

# How long to wait before scoring. Long enough for a price change to show in
# the numbers, short enough that the answer still informs the next decision.
# Matches the day-14 horizon executive.py's docstring already promised.
HORIZON_DAYS = 14
# The window either side of the change that gets compared.
COMPARISON_DAYS = 30

# Agents whose advice attaches to a countable outcome. Everything else is
# recorded as advice and never scored — see the module docstring.
MEASURABLE_AGENTS = {"pricing_intelligence"}


def _item_gross_profit(db: Session, restaurant_id: int, menu_item_id: int,
                       start, end) -> int:
    """Gross profit in cents for one menu item across a window.

    Line revenue minus line cost at the item's CURRENT cost price. Using the
    current cost on both sides of the comparison is deliberate: we are
    measuring the effect of the price change, so holding cost constant is what
    isolates it. An item with no cost price contributes revenue and no cost,
    which is why such items are excluded before this is ever called.
    """
    row = (
        db.query(
            func.coalesce(func.sum(models.OrderItem.quantity * models.OrderItem.unit_price), 0),
            func.coalesce(func.sum(models.OrderItem.quantity), 0),
        )
        .join(models.Order, models.Order.id == models.OrderItem.order_id)
        .filter(
            models.Order.restaurant_id == restaurant_id,
            models.Order.status != models.OrderStatus.CANCELLED,
            models.Order.created_at >= start,
            models.Order.created_at < end,
            models.OrderItem.menu_item_id == menu_item_id,
        )
        .first()
    )
    revenue, qty = int(row[0] or 0), int(row[1] or 0)
    item = db.query(models.MenuItem).filter(models.MenuItem.id == menu_item_id).first()
    cost_price = (item.cost_price or 0) if item else 0
    return revenue - (qty * cost_price)


def record_decision_outcome(
    db: Session, restaurant_id: int, card: dict, decision: str, *,
    horizon_days: int = HORIZON_DAYS,
) -> int | None:
    """Record what was claimed, so it can be checked later.

    Called when the owner approves a card. Returns the AgentPrediction id, or
    None when there is nothing scoreable — no claimed impact, an agent whose
    advice has no countable outcome, or an item with no cost price to measure a
    margin against.

    Never raises: failing to record an outcome must not cost the owner their
    decision.
    """
    if decision != "approved":
        return None
    agent = card.get("agent") or ""
    if agent not in MEASURABLE_AGENTS:
        return None
    if card.get("entity_type") != "menu_item" or not card.get("entity_id"):
        return None

    predicted = card.get("impact_cents_month")
    if not predicted or predicted <= 0:
        return None

    item_id = card["entity_id"]
    item = db.query(models.MenuItem).filter(models.MenuItem.id == item_id).first()
    if item is None or not item.cost_price:
        # No cost price means no measurable margin — the same rule the profit
        # module follows. Scoring against a phantom 100% margin would teach the
        # ranking the wrong lesson.
        return None

    now = utcnow()
    baseline = _item_gross_profit(
        db, restaurant_id, item_id, now - timedelta(days=COMPARISON_DAYS), now)

    try:
        return record_prediction(
            db, restaurant_id, agent, DECISION_IMPACT,
            prediction_date=(now + timedelta(days=horizon_days)).date(),
            predicted=float(predicted),
            metadata={
                "card_key": card.get("id"),
                "action": card.get("title"),
                "menu_item_id": item_id,
                "baseline_profit_cents": baseline,
                "baseline_from": (now - timedelta(days=COMPARISON_DAYS)).isoformat(),
                "decided_at": now.isoformat(),
                "comparison_days": COMPARISON_DAYS,
            },
        )
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("could not record decision outcome for card %s", card.get("id"))
        return None


def evaluate_due_decision_outcomes(
    db: Session, restaurant_id: int, as_of: date | None = None
) -> int:
    """Score every matured, unscored decision. Returns how many were scored.

    The actual figure is the CHANGE in the item's gross profit — the 30 days
    since the decision against the 30 days before it — projected to a month, so
    it is comparable with the monthly impact that was claimed. Comparing the
    post-change profit against the claimed DELTA would score every decision as
    a wild miss regardless of whether it worked.
    """
    today = as_of or utcnow().date()
    due = (
        db.query(models.AgentPrediction)
        .filter(
            models.AgentPrediction.restaurant_id == restaurant_id,
            models.AgentPrediction.prediction_type == DECISION_IMPACT,
            models.AgentPrediction.actual_value.is_(None),
            models.AgentPrediction.prediction_date <= today,
        )
        .all()
    )
    scored = 0
    for pred in due:
        try:
            meta = json.loads(pred.metadata_json or "{}")
        except (TypeError, ValueError):
            meta = {}
        item_id = meta.get("menu_item_id")
        baseline = meta.get("baseline_profit_cents")
        decided_at = meta.get("decided_at")
        if not item_id or baseline is None or not decided_at:
            continue
        try:
            start = utcnow().fromisoformat(decided_at) if isinstance(decided_at, str) else decided_at
        except ValueError:
            continue

        elapsed_days = max((utcnow() - start).days, 1)
        since = _item_gross_profit(db, restaurant_id, item_id, start, utcnow())
        # Both sides scaled to a month so the comparison is like for like.
        since_monthly = since * (30 / elapsed_days)
        baseline_monthly = baseline * (30 / COMPARISON_DAYS)
        actual_delta = since_monthly - baseline_monthly

        evaluate_prediction(db, pred.id, actual=float(round(actual_delta)))
        scored += 1
    return scored


def run_decision_outcome_cycle(db: Session) -> dict:
    """Score matured decisions across every restaurant. Degrades per-restaurant."""
    scored = 0
    for (rid,) in db.query(models.Restaurant.id).all():
        try:
            scored += evaluate_due_decision_outcomes(db, rid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("decision outcome cycle failed for restaurant %s: %s", rid, exc)
    if scored:
        logger.info("decision outcomes scored: %s", scored)
    return {"scored": scored}
