"""GET /api/v1/ai/creative/home — the creative (stochastic) note on Home (ADR 0007).

Home either tells the owner about their day or, when the restaurant data cannot
yet be trusted, about the system. Which of the two is decided HERE, from the same
rule the OS chat and the Home page use (source receiving AND reconciled) — the
creative layer inherits that evidence gate and never widens it:

  verified source   -> `today_story`   evidence: the day's recorded figures
  anything else     -> `system_story`  evidence: what the software does; NO
                                       restaurant figures are ever sent

Deliberately NOT under /overview (Home's own feed) so it loads independently and
can never delay or break it. It lives under /ai, which observer mode blocks.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

import models
from ai import creative
from auth import require_staff_role
from database import get_db
from rate_limit import limiter
from routers import ai_ask, overview

router = APIRouter(prefix="/ai/creative", tags=["ai"])

_WINDOW_LABEL = {
    "1h": "the last hour",
    "today": "today so far (Nairobi time)",
    "7d": "the last 7 days",
    "30d": "the last 30 days",
}

_CONNECTION_IN_WORDS = {
    "receiving": ("MacSoft has started delivering records, but the delivery has not passed a clean "
                  "reconciliation, so restaurant figures are not yet treated as verified."),
    "awaiting_first_delivery": "MacSoft has not delivered any records yet.",
    "unavailable": "The state of the MacSoft connection could not be read right now.",
}


def _source_verified(db: Session) -> tuple[bool, dict]:
    connection = overview._source_connection(db)
    verified = connection.get("state") == "receiving" and connection.get("reconciled") is True
    return verified, connection


def _today_evidence(db: Session, user, rid: int, period: str) -> dict:
    """The day's recorded figures, from the same deterministic helpers Home uses.

    Nothing is computed here beyond what those helpers return, and only facts that
    are really recorded are included: overview's kitchen, waitlist, expiry and
    overtime slots are placeholders, so they are listed as not_available instead
    of being passed on as zeros the model could narrate."""
    start, end = overview._eat_range(period)
    core = overview._summarize(db, rid, start, end)
    op_start, op_end = overview._eat_range("today")
    stock = overview._stock_card(db, rid)
    bookings = overview._bookings_card(db, rid, op_start, op_end)
    staff = overview._staff_card(db, rid, op_start, op_end)
    now_eat = overview._eat_now()

    attention: list[dict] = []
    try:
        # SAVEPOINT: the decision layer's own error handling is not savepointed, so a
        # failing SQL statement inside it would otherwise abort the PostgreSQL
        # transaction and take the metering write down with it.
        with db.begin_nested():
            cards = overview._attention_cards(db, rid, user.tenant_id)
        attention = [{"area": c["domain"], "title": c["title"]} for c in cards[:3]]
    except Exception:
        attention = []

    evidence: dict = {
        "date": now_eat.date().isoformat(),
        "weekday": now_eat.strftime("%A"),
        "sales_window": _WINDOW_LABEL[period],
        "sales": {
            "revenue_kes": round(core["revenue"]),
            "paid_orders": core["orders"],
            "average_order_kes": round(core["revenue"] / core["orders"]) if core["orders"] else None,
        },
        "today_operations": {
            "recorded_stock_items": stock["recorded_items"],
            "low_stock_items": [{"name": i["name"], "quantity_left": i["qty"]} for i in stock["low_stock"][:3]],
            "low_stock_count": len(stock["low_stock"]),
            "confirmed_booking_covers": bookings["covers_today"],
            "shifts_scheduled": staff["scheduled"],
            "shifts_started_not_finished": staff["on_shift"],
        },
        "needs_attention": attention,
        "not_available": ["kitchen speed", "delayed orders", "waitlist", "no-show rate", "expiry", "waste",
                          "overtime risk", "sales pace forecast"],
    }
    if not core["orders"]:
        evidence["sales_note"] = ("No paid orders are recorded for this window. That does not show that no "
                                  "guests came; do not describe it as a quiet or slow day.")
    return evidence


def _system_evidence(connection: dict) -> dict:
    """What the software does. No restaurant figure of any kind."""
    available = list(dict.fromkeys(ai_ask._MODULE_CAPABILITIES.values()))
    planned = [f"{label} (planned, not available yet)" for label in ai_ask._PLANNED_OS_AREAS.values()]
    return {
        "available_areas": available,
        "planned_areas": planned,
        "data_connection": _CONNECTION_IN_WORDS.get(connection.get("state"), _CONNECTION_IN_WORDS["unavailable"]),
        "boundaries": [
            "The connection to MacSoft is read-only: this system never writes changes back to it.",
            "Decisions and approvals are recorded for review; the system does not execute them.",
            "Restaurant analysis needs verified records; until then the software can only be described, not applied to the restaurant.",
        ],
    }


@router.get("/home")
@limiter.limit("20/minute")
def creative_home(
    request: Request,
    period: str = Query("today", pattern="^(1h|today|7d|30d)$"),
    refresh: bool = False,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_staff_role()),
):
    rid = overview._restaurant_id(db, user)
    if not rid:
        raise HTTPException(404, "No restaurant found for this account")
    verified, connection = _source_verified(db)
    if verified:
        # A "today" story must never be served on a later calendar day.
        valid_since = overview._eat_range("today")[0] if period == "today" else None
        return creative.take(
            db, user, rid, surface=creative.SURFACE_HOME, period=period, mode=creative.MODE_TODAY_STORY,
            evidence=lambda: _today_evidence(db, user, rid, period), refresh=refresh, valid_since=valid_since,
        )
    return creative.take(
        db, user, rid, surface=creative.SURFACE_HOME, period="any", mode=creative.MODE_SYSTEM_STORY,
        evidence=lambda: _system_evidence(connection), refresh=refresh,
    )
