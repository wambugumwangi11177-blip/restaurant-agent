"""GET /api/v1/ai/creative/home — the creative (stochastic) note on Home (ADR 0007).

Home either tells the owner about their day or, when the restaurant data cannot
yet be trusted, about the system. Which of the two is decided HERE, from the same
rule the OS chat uses (`overview.source_is_trusted`: a MacSoft feed that is
receiving AND reconciled, or a tenant that records directly in this app) — the
creative layer inherits that evidence gate and never widens it:

  trusted source    -> `today_story`   evidence: the day's recorded figures
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

_CONNECTION_IN_WORDS = {
    "receiving": ("MacSoft has started delivering records, but the delivery has not passed a clean "
                  "reconciliation, so restaurant figures are not yet treated as verified."),
    "awaiting_first_delivery": "MacSoft has not delivered any records yet.",
    "unavailable": "The state of the MacSoft connection could not be read right now.",
    "direct": "This restaurant records its data directly in this system; there is no external feed to wait for.",
}


def _source_verified(db: Session, tenant_id: int | None) -> tuple[bool, dict]:
    """(trusted, connection) — the one rule the OS chat and Home already share.

    Delegates to overview.source_is_trusted so a tenant that records directly in
    this app (overview.DIRECT_SOURCE_TENANTS) counts as trusted exactly as it does
    in the OS chat, instead of being held to a MacSoft reconciliation it never has."""
    connection = overview._source_connection(db, tenant_id)
    return overview.source_is_trusted(connection), connection


def _today_evidence(db: Session, user, rid: int, period: str) -> dict:
    """The day's recorded figures, from the same deterministic helpers Home uses.

    Nothing is computed here beyond what those helpers return, and only facts that
    are really recorded are included: overview's kitchen, waitlist, expiry and
    overtime slots are placeholders, so they are listed as not_available instead
    of being passed on as zeros the model could narrate."""
    from time_utils import period_label, trading_window
    start, end, service = trading_window(period)
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
        attention = [{"area": c["domain"], "title": creative.clean_dish_name(c["title"]),
                      "why": c.get("why") or "", "period": c.get("period") or "see why"} for c in cards[:3]]
    except Exception:
        attention = []

    evidence: dict = {
        "date": (service or now_eat.date()).isoformat(),
        "weekday": (service or now_eat.date()).strftime("%A"),
        "sales_window": period_label(period),
        "sales": {
            "period": period_label(period),
            "revenue_kes": round(core["revenue"]),
            "paid_orders": core["orders"],
            "average_order_kes": round(core["revenue"] / core["orders"]) if core["orders"] else None,
        },
        "today_operations": {
            "period": "the Nairobi calendar day (bookings and shifts; not the sales service day)",
            "recorded_stock_items": stock["recorded_items"],
            "low_stock_items": [{"name": creative.clean_dish_name(i["name"]), "quantity_left": i["qty"],
                                 "period": "quantity on hand now"} for i in stock["low_stock"][:3]],
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
    verified, connection = _source_verified(db, user.tenant_id)
    if verified:
        # A "today" story must never be served on a later calendar day.
        if period == "today":
            from time_utils import service_sales_window
            valid_since = service_sales_window()[0]
        else:
            valid_since = None
        return creative.take(
            db, user, rid, surface=creative.SURFACE_HOME, period=period, mode=creative.MODE_TODAY_STORY,
            evidence=lambda: _today_evidence(db, user, rid, period), refresh=refresh, valid_since=valid_since,
        )
    return creative.take(
        db, user, rid, surface=creative.SURFACE_HOME, period="any", mode=creative.MODE_SYSTEM_STORY,
        evidence=lambda: _system_evidence(connection), refresh=refresh,
    )
