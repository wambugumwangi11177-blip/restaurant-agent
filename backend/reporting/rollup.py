"""Daily fact rollups for the report windows.

WHY THIS EXISTS
───────────────
routers/reports.py aggregates directly off `orders` and `order_items`. Measured
on a seeded 300,000-order / 900,000-line-item dataset, the YEARLY report cost
about 2.5 s of database work; after the single-pass `_summarize` rewrite and the
covering index on order_items it is about 1.6 s. Both of those were real wins and
neither changes the shape of the problem: the cost grows with the number of rows
in the window, and a yearly window is every row.

A daily fact table changes the shape. 365 pre-aggregated rows replace 300,000
orders and 900,000 line items.

THE TWO THINGS THAT MAKE THIS DANGEROUS
───────────────────────────────────────
1. WINDOW EDGES DO NOT LAND ON DAYS. `routers/reports.py::_range` builds a
   ROLLING window — "now minus 7 days" — not a calendar week. So a report window
   starts and ends mid-day. A daily fact cannot answer that on its own. Every
   read here therefore splits the window into three parts: a partial head day
   answered live, a run of whole days answered from facts, and a partial tail day
   answered live. Each partial is at most one day of orders.

2. FACTS GO STALE. An order mutates after it is created — `is_paid` flips when
   payment lands, `status` becomes CANCELLED. A rollup that appends yesterday and
   never looks back will drift away from the source. `refresh_trailing` therefore
   RE-AGGREGATES a trailing window instead of appending, and `verify` compares
   facts against the live query so drift is detected rather than served.

Because of (2) these tables are a CACHE, never a source of truth. Every read
falls back to the live query when the facts do not fully cover the window.

DAY BOUNDARY
────────────
`business_date` is the Africa/Nairobi calendar day, matching `_EAT_OFFSET` in
routers/reports.py. One Nairobi day is [21:00 previous day, 21:00) UTC. Keying on
the UTC date instead would put three hours of orders on the wrong day, which on a
revenue line is a wrong number shown to the owner, not a rounding error.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from time_utils import utcnow

# Africa/Nairobi is UTC+3 year round — no DST. Same constant routers/reports.py
# uses; kept in sync deliberately rather than imported, to avoid reporting/
# importing from routers/ and creating a cycle.
EAT_OFFSET = timedelta(hours=3)


# ── day arithmetic ──────────────────────────────────────────────────────────
def business_date_of(moment_utc_naive: datetime) -> date:
    """The Nairobi calendar day a UTC-naive timestamp falls in."""
    return (moment_utc_naive + EAT_OFFSET).date()


def day_bounds_utc(business_day: date) -> tuple[datetime, datetime]:
    """[start, end) of one Nairobi day, as UTC-naive timestamps."""
    start_eat = datetime(business_day.year, business_day.month, business_day.day)
    return start_eat - EAT_OFFSET, start_eat + timedelta(days=1) - EAT_OFFSET


def _paid_order_filter(rid: int, start: datetime, end: datetime):
    """The single definition of 'countable revenue', shared by the fact builder
    and the live fallback so the two can never drift apart by wording."""
    return (
        models.Order.restaurant_id == rid,
        models.Order.created_at >= start,
        models.Order.created_at < end,
        models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
    )


def _whole_day_span(start: datetime, end: datetime) -> tuple[date | None, date | None]:
    """The run of Nairobi days lying ENTIRELY inside [start, end), or (None, None).

    A day qualifies only if both its bounds sit within the window, so a partial
    head or tail day is never answered from a fact row that also covers hours
    outside the caller's window.
    """
    first = business_date_of(start)
    if day_bounds_utc(first)[0] < start:
        first = first + timedelta(days=1)
    last = business_date_of(end - timedelta(microseconds=1))
    if day_bounds_utc(last)[1] > end:
        last = last - timedelta(days=1)
    if first > last:
        return None, None
    return first, last


# ── building ────────────────────────────────────────────────────────────────
def rebuild_days(db: Session, rid: int, days: list[date], commit: bool = True) -> int:
    """Recompute both fact grains for `days`, replacing whatever was there.

    A DailySalesFact row is written for EVERY requested day, including days with
    no sales. That is what makes presence mean "built": without it, a zero-sales
    day and a never-built day look identical, and a read would silently serve a
    window with a hole in it.
    """
    if not days:
        return 0
    now = utcnow()
    for d in days:
        start, end = day_bounds_utc(d)

        revenue, orders = db.query(
            func.coalesce(func.sum(models.Order.total), 0),
            func.count(models.Order.id),
        ).filter(*_paid_order_filter(rid, start, end)).one()

        row = db.query(models.DailySalesFact).filter(
            models.DailySalesFact.restaurant_id == rid,
            models.DailySalesFact.business_date == d,
        ).first()
        if row is None:
            row = models.DailySalesFact(restaurant_id=rid, business_date=d)
            db.add(row)
        row.revenue_cents = int(revenue or 0)
        row.order_count = int(orders or 0)
        row.built_at = now

        # Item grain. Deleted and rewritten rather than updated in place: an item
        # that sold yesterday and was then refunded to zero must LOSE its row,
        # and an upsert-only path would leave the stale row behind.
        db.query(models.DailyItemSalesFact).filter(
            models.DailyItemSalesFact.restaurant_id == rid,
            models.DailyItemSalesFact.business_date == d,
        ).delete(synchronize_session=False)

        item_rows = db.query(
            models.OrderItem.menu_item_id,
            func.sum(models.OrderItem.quantity),
            func.sum(models.OrderItem.unit_price * models.OrderItem.quantity),
        ).join(models.Order, models.OrderItem.order_id == models.Order.id
        ).filter(*_paid_order_filter(rid, start, end)
        ).group_by(models.OrderItem.menu_item_id).all()

        for menu_item_id, qty, sales in item_rows:
            if menu_item_id is None:
                continue
            db.add(models.DailyItemSalesFact(
                restaurant_id=rid, business_date=d, menu_item_id=menu_item_id,
                qty=int(qty or 0), sales_cents=int(sales or 0), built_at=now))

        db.flush()

    if commit:
        db.commit()
    return len(days)


def refresh_trailing(db: Session, rid: int, days: int = 7) -> int:
    """Re-aggregate the last `days` COMPLETE Nairobi days.

    Trailing rather than incremental, because an order created several days ago
    can still flip to paid or cancelled today. Today itself is deliberately not
    built: it is still accumulating, and reads answer the current day live.
    """
    today = business_date_of(utcnow())
    targets = [today - timedelta(days=n) for n in range(1, days + 1)]
    return rebuild_days(db, rid, sorted(targets))


def backfill(db: Session, rid: int, since: date | None = None) -> int:
    """Build every complete day from the restaurant's first paid order onward."""
    first_order = db.query(func.min(models.Order.created_at)).filter(
        models.Order.restaurant_id == rid).scalar()
    if first_order is None:
        return 0
    start_day = since or business_date_of(first_order)
    today = business_date_of(utcnow())
    days, d = [], start_day
    while d < today:
        days.append(d)
        d += timedelta(days=1)
    return rebuild_days(db, rid, days)


# ── coverage ────────────────────────────────────────────────────────────────
def _covered(db: Session, rid: int, first: date, last: date) -> bool:
    """True only if EVERY day in [first, last] has a built fact row."""
    expected = (last - first).days + 1
    got = db.query(func.count(models.DailySalesFact.id)).filter(
        models.DailySalesFact.restaurant_id == rid,
        models.DailySalesFact.business_date >= first,
        models.DailySalesFact.business_date <= last,
    ).scalar()
    return int(got or 0) == expected


# ── live (fallback) aggregates ──────────────────────────────────────────────
def _live_summarize(db: Session, rid: int, start: datetime, end: datetime):
    if start >= end:
        return 0, 0
    revenue, orders = db.query(
        func.coalesce(func.sum(models.Order.total), 0),
        func.count(models.Order.id),
    ).filter(*_paid_order_filter(rid, start, end)).one()
    return int(revenue or 0), int(orders or 0)


def _live_item_totals(db: Session, rid: int, start: datetime, end: datetime) -> dict:
    """ALL items in the span, keyed by menu item NAME — never a top-N slice.

    Truncating a partial span to its own top 5 would drop an item that is top 5
    over the whole window but sixth in that span, so the merged ranking would be
    wrong. Keyed by name because the live query groups by name.
    """
    if start >= end:
        return {}
    rows = db.query(
        models.MenuItem.name,
        func.sum(models.OrderItem.quantity),
        func.sum(models.OrderItem.unit_price * models.OrderItem.quantity),
    ).join(models.Order, models.OrderItem.order_id == models.Order.id
    ).join(models.MenuItem, models.OrderItem.menu_item_id == models.MenuItem.id
    ).filter(*_paid_order_filter(rid, start, end)
    ).group_by(models.MenuItem.name).all()
    return {name: (int(q or 0), int(s or 0)) for name, q, s in rows}


# ── reads ───────────────────────────────────────────────────────────────────
def summarize(db: Session, rid: int, start: datetime, end: datetime) -> dict:
    """Revenue and order count for [start, end), facts where possible.

    Returns the same shape as routers.overview._summarize and must return the
    same NUMBERS — tests/test_reporting_rollup.py pins that across random
    windows. Falls back entirely to the live query when facts do not cover the
    whole-day run.
    """
    first, last = _whole_day_span(start, end)
    if first is None or not _covered(db, rid, first, last):
        revenue, orders = _live_summarize(db, rid, start, end)
        return {"revenue": revenue / 100.0, "orders": orders, "source": "live"}

    sealed_rev, sealed_cnt = db.query(
        func.coalesce(func.sum(models.DailySalesFact.revenue_cents), 0),
        func.coalesce(func.sum(models.DailySalesFact.order_count), 0),
    ).filter(
        models.DailySalesFact.restaurant_id == rid,
        models.DailySalesFact.business_date >= first,
        models.DailySalesFact.business_date <= last,
    ).one()

    head_rev, head_cnt = _live_summarize(db, rid, start, day_bounds_utc(first)[0])
    tail_rev, tail_cnt = _live_summarize(db, rid, day_bounds_utc(last)[1], end)

    revenue = int(sealed_rev or 0) + head_rev + tail_rev
    orders = int(sealed_cnt or 0) + head_cnt + tail_cnt
    return {"revenue": revenue / 100.0, "orders": orders, "source": "facts"}


def top_items(db: Session, rid: int, start: datetime, end: datetime, limit: int = 5) -> list:
    """Top `limit` menu items for [start, end), facts where possible."""
    first, last = _whole_day_span(start, end)
    if first is None or not _covered(db, rid, first, last):
        merged = _live_item_totals(db, rid, start, end)
    else:
        rows = db.query(
            models.MenuItem.name,
            func.sum(models.DailyItemSalesFact.qty),
            func.sum(models.DailyItemSalesFact.sales_cents),
        ).join(models.MenuItem,
               models.DailyItemSalesFact.menu_item_id == models.MenuItem.id
        ).filter(
            models.DailyItemSalesFact.restaurant_id == rid,
            models.DailyItemSalesFact.business_date >= first,
            models.DailyItemSalesFact.business_date <= last,
        ).group_by(models.MenuItem.name).all()
        merged = {name: (int(q or 0), int(s or 0)) for name, q, s in rows}

        for span in ((start, day_bounds_utc(first)[0]),
                     (day_bounds_utc(last)[1], end)):
            for name, (q, s) in _live_item_totals(db, rid, *span).items():
                pq, ps = merged.get(name, (0, 0))
                merged[name] = (pq + q, ps + s)

    # Sort AFTER merging, then slice — see _live_item_totals on why the parts are
    # never pre-truncated. Quantity descending, then NAME ASCENDING: the same
    # tiebreak routers/reports.py::_top_items now applies, so the two paths
    # cannot disagree on items that sold equally.
    ordered = sorted(merged.items(), key=lambda kv: (-kv[1][0], kv[0]))[:limit]
    return [{"name": n, "qty": q, "sales_kes": s / 100.0} for n, (q, s) in ordered]


# ── drift detection ─────────────────────────────────────────────────────────
def verify(db: Session, rid: int, start: datetime, end: datetime) -> dict:
    """Compare the fact-backed answer with the live one over the same window.

    The facts are a cache of a query, so the only honest way to trust them is to
    re-run the query and check. Mirrors the count-and-checksum posture of
    integration/reconcile.py: a run that cannot prove equality reports a
    mismatch rather than a clean result.
    """
    live_rev, live_cnt = _live_summarize(db, rid, start, end)
    fact = summarize(db, rid, start, end)
    rev_drift = round(fact["revenue"] - live_rev / 100.0, 2)
    cnt_drift = fact["orders"] - live_cnt
    return {
        "status": "clean" if (rev_drift == 0 and cnt_drift == 0) else "mismatch",
        "source": fact["source"],
        "revenue_drift_kes": rev_drift,
        "order_count_drift": cnt_drift,
        "window": [start.isoformat(), end.isoformat()],
    }
