"""
backend/owner/home.py — GET /owner/home (docs/v2/SPEC.md §3.1): everything of value on one page.

  zone 1  pulse               today's sales vs the same weekday, trend, costs covered, money match, freshness
  zone 2  costing_you_money   top 5 things costing money, each with KES, one action, why, the rule used
  zone 3  health              six tiles, one per area: a number, a word, a colour
  areas   the six area panels (owner/areas.py): collapsed to one line on Home, same block on /owner/area/{key}
  zone 4  coming_up           bills, licences, deliveries, bookings
  zone 5  read                LEVIII's AI-written note (optional; absent unless every number in it is backed)

Every block has `state`, `as_of` and — where a rule was used — `assumption: {setting, value}` (owner/states.py).
Money is KES at this edge (integer cents inside); nothing here is computed in a router.
"""
from __future__ import annotations

from datetime import timedelta

import models
from ai.analysis_clock import data_freshness
from owner import areas
from owner.states import OwnerContext, block, iso, kes, no_data, unavailable

PERIODS = ("today", "7d", "30d")


def _overview():
    from routers import overview
    return overview


def _mpesa_summary(b: dict) -> dict:
    """Zone 1 carries the totals, not the lists: the sentence, how many sales and payments have no match and what they add up to."""
    if b.get("state") in ("no_data", "unavailable"):
        return b
    keep = {k: b[k] for k in ("state", "as_of", "source", "headline", "checked", "matched", "outside_statement", "assumption") if k in b}
    return {**keep, "sales_without_payment": {k: b["sales_without_payment"][k] for k in ("count", "kes")},
            "payments_without_sale": {k: b["payments_without_sale"][k] for k in ("count", "kes")}, "different_amounts": len(b["different_amounts"])}


def _pulse(ctx: OwnerContext, period: str) -> dict:
    overview = _overview()
    start, end = overview._eat_range("today")
    today = overview._summarize(ctx.db, ctx.rid, start, end)
    base = ctx.order_state()
    # Same weekday last week, over the same elapsed part of the day: a fair comparison at 3 pm.
    last_week = overview._summarize(ctx.db, ctx.rid, start - timedelta(days=7), end - timedelta(days=7))
    vs = round((today["revenue"] - last_week["revenue"]) / last_week["revenue"] * 100, 1) if last_week["revenue"] else None
    win_start, win_end = overview._eat_range(period)
    window = overview._summarize(ctx.db, ctx.rid, win_start, win_end)
    shifts = ctx.cached("cash_shifts", lambda: areas._shifts(ctx))
    if shifts["state"] in ("no_data", "unavailable"):
        cash = {k: shifts[k] for k in ("state", "as_of", "reason") if k in shifts}
    else:
        cash = block(shifts["state"], as_of=shifts.get("as_of"), checked=len(shifts.get("shifts", [])),
                     to_check=sum(1 for s in shifts.get("shifts", []) if s["check"]),
                     **({"entered_up_to": shifts["entered_up_to"]} if "entered_up_to" in shifts else {}))
    freshness = ctx.cached("freshness", lambda: data_freshness(ctx.db, ctx.rid, ctx.latest_order_at))
    conn = overview._source_connection(ctx.db, ctx.tenant_id)
    return {**base,
            "sales_today": today["revenue"], "orders_today": today["orders"],
            "vs_same_weekday_pct": vs,
            "vs_same_weekday_state": "live" if vs is not None else "learning",
            "sales_in_period": window["revenue"], "orders_in_period": window["orders"],
            "trend_7d": [{"date": d["date"], "sales": d["revenue"], "orders": d["orders"]} for d in overview._performance(ctx.db, ctx.rid)["revenue_trend"]],
            "breakeven_at": ctx.safe("home.breakeven", lambda: areas.breakeven_summary(ctx)),
            "money_match": {"cash": cash, "mpesa": _mpesa_summary(areas._mpesa(ctx))},
            "freshness": {"latest_sale_at": freshness["latest_order_at"], "data_age_days": freshness["data_age_days"],
                          "is_stale": freshness["is_stale"], "source": conn["source"], "source_state": conn["state"],
                          "source_reconciled": bool(conn.get("reconciled")), "source_trusted": overview.source_is_trusted(conn),
                          "source_notice": overview._SOURCE_NOTICE.get(conn["state"], ""),
                          "source_records": conn.get("records"), "source_last_received_at": conn.get("last_received_at")}}


CARDS_SHOWN = 5
DECISION_OPTIONS = ["approved", "later", "rejected"]          # acknowledge · remind me in 24h · dismiss (routers/overview.py)


def _rank(cards: list[dict]) -> list[dict]:
    """What is happening now first (as it always was); then money that is already going out, most first; then money you could
    make, most first; then what we cannot put an honest figure on, in the order it came. "Costing you money" is about the
    second group, so a price rise worth KES 6,000 does not sit above a gap that has already cost KES 2,000; and a card without
    a figure never outranks one with a figure."""
    now = [c for c in cards if c.get("now")]
    rest = [c for c in cards if not c.get("now")]
    priced = [c for c in rest if (c.get("impact_cents_month") or 0) > 0]
    by_kes = lambda group: sorted(group, key=lambda c: c["impact_cents_month"], reverse=True)   # noqa: E731
    losses = by_kes(c for c in priced if c.get("kind") == "loss")
    ideas = by_kes(c for c in priced if c.get("kind") != "loss")
    unpriced = [c for c in rest if not (c.get("impact_cents_month") or 0) > 0]
    return now + losses + ideas + unpriced


def _card(c: dict) -> dict:
    return {"id": c["id"], "domain": c["domain"], "sentence": c["title"], "kes_month": kes(c.get("impact_cents_month") or None),
            "action": c.get("what_to_do", ""), "why": c.get("why", ""), "assumption": c.get("assumption"),
            "decision": {"options": DECISION_OPTIONS}, "tier": "now" if c.get("now") else ("loss" if c.get("kind") == "loss" else "idea")}


def ranked_cards(ctx: OwnerContext) -> list[dict]:
    """Every card, in Home's order (internal shape: `title`, `impact_cents_month`, `kind` …). Home shows the first five; the settings
    preview compares the whole list before and after a proposed change."""
    return _rank(_overview()._attention_cards(ctx.db, ctx.rid, ctx.tenant_id, decision_limit=40))


def _costing_you_money(ctx: OwnerContext) -> dict:
    base = ctx.order_state()
    cards = ranked_cards(ctx)
    if base["state"] == "no_data" and not cards:
        return no_data("Nothing to rank until sales are recorded.", cards=[])
    top = cards[:CARDS_SHOWN]
    return {**(base if base["state"] != "no_data" else block("live", as_of=ctx.now)),
            "cards": [_card(c) for c in top],
            # Every card, ranked — what Home folds under "more" and what Ask LEVIII's "what should I do" starts from.
            "ranked": [{k: _card(c)[k] for k in ("id", "domain", "sentence", "kes_month", "tier")} for c in cards],
            "more": max(len(cards) - len(top), 0),
            "ranking": "What is happening now first, then ideas by what they are worth in KES; an idea we cannot put a number on comes after those we can.",
            "reason": None if top else "Nothing is costing you money that we can see right now."}


def _health(ctx: OwnerContext, area_blocks: dict) -> dict:
    tiles = [{"area": key, "title": area["title"], **area["summary"]} for key, area in area_blocks.items()]
    known = any(t["number"] is not None for t in tiles)
    return block("live" if known else "no_data", as_of=ctx.now, tiles=tiles,
                 reason=None if known else "The tiles fill in as sales and costs are recorded.")


def _coming_up(ctx: OwnerContext) -> dict:
    overview = _overview()
    deliveries = ctx.db.query(models.PurchaseOrder).filter(
        models.PurchaseOrder.restaurant_id == ctx.rid, models.PurchaseOrder.status.in_(("PENDING", "SENT"))
    ).order_by(models.PurchaseOrder.expected_at.asc()).limit(10).all()
    start, end = overview._eat_range("today")
    bookings = overview._bookings_card(ctx.db, ctx.rid, start, end)
    return {
        "bills": ctx.safe("coming_up.bills", lambda: areas.bills_due_block(ctx)),
        "licences": ctx.safe("coming_up.licences", lambda: areas.licences_due_block(ctx)),
        "deliveries": block("as_entered" if deliveries else "no_data", as_of=ctx.now, reason=None if deliveries else "No deliveries expected.",
                            items=[{"item": d.inventory_item.item_name if d.inventory_item else "", "supplier": d.supplier.name if d.supplier else "",
                                    "expected_at": iso(d.expected_at), "status": d.status} for d in deliveries]),
        "bookings": _bookings(ctx, bookings["covers_today"]),
    }


def _bookings(ctx: OwnerContext, covers_today: int, days: int = 7) -> dict:
    """Tonight's covers, and the days ahead that have bookings (so a quiet evening still shows what is coming)."""
    from collections import defaultdict
    from datetime import datetime as _dt
    from time_utils import EAT_OFFSET, eat_date
    local_now = ctx.now + EAT_OFFSET
    today = eat_date(ctx.now)
    rows = ctx.db.query(models.Reservation.reservation_date, models.Reservation.reservation_time, models.Reservation.party_size).filter(
        models.Reservation.restaurant_id == ctx.rid, models.Reservation.status == models.ReservationStatus.CONFIRMED,
        models.Reservation.reservation_date >= today, models.Reservation.reservation_date < today + timedelta(days=days)).all()
    per_day: dict = defaultdict(lambda: [0, 0])
    for d, t, size in rows:
        if _dt.combine(d, t) >= local_now:
            per_day[d][0] += 1
            per_day[d][1] += int(size or 0)
    ahead = [{"date": d.isoformat(), "bookings": n, "covers": c} for d, (n, c) in sorted(per_day.items())]
    if not covers_today and not ahead:
        return no_data(f"No bookings in the next {days} days.", covers_today=0, next_days=[])
    return block("live", as_of=ctx.now, covers_today=covers_today, next_days=ahead,
                 reason=None if covers_today else "No bookings tonight." if ahead else None)


def _read(ctx: OwnerContext) -> dict:
    import feature_flags
    if not feature_flags.is_enabled("ai_narration"):
        return unavailable("LEVIII's read is switched off.", text=None)
    return unavailable("LEVIII's read has not been written yet.", text=None)


def _setup(ctx: OwnerContext) -> dict:
    """What the first-run screens need: has the owner chosen their targets, and how old is the restaurant — in Nairobi days since the
    earlier of the day its tenant joined and its first recorded sale (a restaurant that arrives with a history is not new). The
    guided first week and the "Your targets" step are driven by these two facts."""
    from sqlalchemy import func

    from time_utils import eat_date
    joined = ctx.db.query(models.Tenant.created_at).filter(models.Tenant.id == ctx.tenant_id).scalar()
    first_sale = ctx.db.query(func.min(models.Order.created_at)).filter(models.Order.restaurant_id == ctx.rid).scalar()
    began = min((d for d in (joined, first_sale) if d is not None), default=None)
    age = max((eat_date(ctx.now) - eat_date(began)).days, 0) if began else 0
    return {"targets_chosen": ctx.db.query(models.RestaurantSettings.id).filter(models.RestaurantSettings.restaurant_id == ctx.rid).first() is not None,
            "age_days": age}


def compose_home(ctx: OwnerContext, period: str = "today") -> dict:
    if period not in PERIODS:
        raise ValueError(f"period must be one of {PERIODS}")
    area_blocks = {key: areas.compose_area(ctx, key) for key in areas.AREAS}
    return {
        "restaurant": {"id": ctx.rid, "name": ctx.restaurant.name},
        "period": period,
        "timezone": "Africa/Nairobi",
        "generated_at": iso(ctx.now),
        "pulse": ctx.safe("home.pulse", lambda: _pulse(ctx, period)),
        "costing_you_money": ctx.safe("home.costing_you_money", lambda: _costing_you_money(ctx)),
        "health": _health(ctx, area_blocks),
        "areas": area_blocks,
        "coming_up": ctx.safe("home.coming_up", lambda: _coming_up(ctx)),
        "read": _read(ctx),
        "setup": _setup(ctx),
    }
