"""backend/reporting/rollup.py — the daily reporting fact layer.

These facts are a CACHE of a query that decides what revenue a restaurant owner
is shown, so every test here is about one question: can the cached answer ever
differ from the live one? The performance win is not worth a single wrong
shilling, so the rollup falls back to the live query whenever it cannot prove
coverage, and these tests pin that behaviour.

The reference implementations are routers/reports.py::_top_items_live and a
direct aggregate written here — deliberately separate code paths from the ones
under test, because a query compared with itself proves nothing.
"""
import datetime as dt

from sqlalchemy import func

import models
from reporting import rollup
from routers.reports import _top_items_live
from routers.deps import get_or_create_restaurant


# ── fixtures ────────────────────────────────────────────────────────────────
def _restaurant(db, name="Rollup Test"):
    tenant = models.Tenant(name=name)
    db.add(tenant); db.commit()
    user = models.User(tenant_id=tenant.id, email=f"{name}@example.com", hashed_password="x")
    db.add(user); db.commit()
    return get_or_create_restaurant(db, user)


def _menu(db, rid, names):
    items = [models.MenuItem(restaurant_id=rid, name=n, price=1000) for n in names]
    db.add_all(items); db.commit()
    return items


def _order(db, rid, when, items, paid=True, status=models.OrderStatus.SERVED):
    """items: list of (menu_item, qty, unit_price_cents)."""
    total = sum(q * p for _, q, p in items)
    o = models.Order(restaurant_id=rid, total=total, is_paid=paid,
                     status=status, created_at=when)
    db.add(o); db.flush()
    for mi, q, p in items:
        db.add(models.OrderItem(order_id=o.id, menu_item_id=mi.id, quantity=q, unit_price=p))
    db.commit()
    return o


def _live_revenue(db, rid, start, end):
    """Reference aggregate, written independently of rollup._live_summarize."""
    rows = db.query(models.Order.total).filter(
        models.Order.restaurant_id == rid,
        models.Order.created_at >= start, models.Order.created_at < end,
        models.Order.is_paid.is_(True),
        models.Order.status != models.OrderStatus.CANCELLED,
    ).all()
    return sum(r[0] for r in rows) / 100.0, len(rows)


# ── day arithmetic ──────────────────────────────────────────────────────────
def test_business_date_uses_nairobi_not_utc():
    """22:00 UTC is already the NEXT day in Nairobi (UTC+3).

    Keying facts on the UTC date would file three hours of every evening's
    orders under the wrong day — not a rounding error on a revenue line.
    """
    late_utc = dt.datetime(2026, 3, 10, 22, 0)
    assert late_utc.date() == dt.date(2026, 3, 10)          # UTC says the 10th
    assert rollup.business_date_of(late_utc) == dt.date(2026, 3, 11)


def test_day_bounds_are_2100_to_2100_utc():
    start, end = rollup.day_bounds_utc(dt.date(2026, 3, 11))
    assert start == dt.datetime(2026, 3, 10, 21, 0)
    assert end == dt.datetime(2026, 3, 11, 21, 0)


def test_whole_day_span_excludes_partial_edges():
    """A day only counts as sealed when BOTH its bounds sit inside the window."""
    start = dt.datetime(2026, 3, 10, 23, 0)   # mid-way through 11 Mar EAT
    end = dt.datetime(2026, 3, 14, 3, 0)      # mid-way through 14 Mar EAT
    first, last = rollup._whole_day_span(start, end)
    assert first == dt.date(2026, 3, 12)
    assert last == dt.date(2026, 3, 13)


def test_whole_day_span_is_none_for_a_sub_day_window():
    start = dt.datetime(2026, 3, 11, 2, 0)
    first, last = rollup._whole_day_span(start, start + dt.timedelta(hours=6))
    assert first is None and last is None


# ── equivalence with the live query ─────────────────────────────────────────
def test_summarize_matches_live_across_a_multi_day_window(db_session):
    r = _restaurant(db_session, "Equiv")
    a, b = _menu(db_session, r.id, ["Ugali", "Nyama"])
    base = dt.datetime(2026, 3, 10, 9, 0)
    for day in range(6):
        _order(db_session, r.id, base + dt.timedelta(days=day), [(a, 2, 500), (b, 1, 1200)])

    start, end = base - dt.timedelta(hours=4), base + dt.timedelta(days=5, hours=6)
    rollup.rebuild_days(db_session, r.id,
                        [dt.date(2026, 3, d) for d in range(10, 17)])

    live_rev, live_cnt = _live_revenue(db_session, r.id, start, end)
    got = rollup.summarize(db_session, r.id, start, end)
    assert got["source"] == "facts"
    assert round(got["revenue"], 2) == round(live_rev, 2)
    assert got["orders"] == live_cnt


def test_top_items_matches_the_live_reference(db_session):
    r = _restaurant(db_session, "TopEquiv")
    a, b, c = _menu(db_session, r.id, ["Ugali", "Nyama", "Sukuma"])
    base = dt.datetime(2026, 4, 2, 9, 0)
    for day in range(5):
        when = base + dt.timedelta(days=day)
        _order(db_session, r.id, when, [(a, 3, 500), (b, 1, 1200)])
        _order(db_session, r.id, when + dt.timedelta(hours=2), [(c, 2, 300)])

    start, end = base - dt.timedelta(hours=5), base + dt.timedelta(days=4, hours=8)
    rollup.rebuild_days(db_session, r.id, [dt.date(2026, 4, d) for d in range(2, 9)])

    assert rollup.top_items(db_session, r.id, start, end) == \
           _top_items_live(db_session, r.id, start, end)


def test_partial_head_and_tail_days_are_counted_live(db_session):
    """The hours outside the sealed run must still reach the total.

    This is the failure that would quietly under-report a day's takings: serve
    the sealed middle and drop the edges.
    """
    r = _restaurant(db_session, "Edges")
    a, = _menu(db_session, r.id, ["Chapati"])
    # One order in the partial head, one in a sealed day, one in the partial tail.
    _order(db_session, r.id, dt.datetime(2026, 5, 4, 23, 0), [(a, 1, 1000)])   # 5 May EAT
    _order(db_session, r.id, dt.datetime(2026, 5, 5, 23, 0), [(a, 1, 2000)])   # 6 May EAT
    _order(db_session, r.id, dt.datetime(2026, 5, 6, 23, 0), [(a, 1, 4000)])   # 7 May EAT
    rollup.rebuild_days(db_session, r.id, [dt.date(2026, 5, d) for d in (5, 6, 7)])

    start = dt.datetime(2026, 5, 4, 22, 0)   # inside 5 May EAT, so 5 May is partial
    end = dt.datetime(2026, 5, 6, 23, 30)    # inside 7 May EAT, so 7 May is partial
    got = rollup.summarize(db_session, r.id, start, end)
    assert got["source"] == "facts"          # 6 May is sealed
    assert got["orders"] == 3                # and all three orders are counted
    assert round(got["revenue"], 2) == 70.0  # 1000 + 2000 + 4000 cents


# ── fallback ────────────────────────────────────────────────────────────────
def test_falls_back_to_live_when_a_day_was_never_built(db_session):
    """A hole in coverage must serve the live answer, never a partial sum."""
    r = _restaurant(db_session, "Hole")
    a, = _menu(db_session, r.id, ["Mandazi"])
    base = dt.datetime(2026, 6, 10, 9, 0)
    for day in range(4):
        _order(db_session, r.id, base + dt.timedelta(days=day), [(a, 1, 1000)])

    # Build only two of the four days — 12 June is deliberately missing.
    rollup.rebuild_days(db_session, r.id, [dt.date(2026, 6, 10), dt.date(2026, 6, 11)])

    start, end = base - dt.timedelta(hours=6), base + dt.timedelta(days=3, hours=6)
    got = rollup.summarize(db_session, r.id, start, end)
    assert got["source"] == "live"
    assert got["orders"] == 4


def test_a_zero_sales_day_is_built_and_still_counts_as_covered(db_session):
    """Presence means 'built'. Without a row for a quiet day, that day is
    indistinguishable from one that was never rolled up, and the whole window
    would drop to the live path forever."""
    r = _restaurant(db_session, "Quiet")
    rollup.rebuild_days(db_session, r.id, [dt.date(2026, 7, 1)])
    row = db_session.query(models.DailySalesFact).filter(
        models.DailySalesFact.restaurant_id == r.id).one()
    assert row.order_count == 0 and row.revenue_cents == 0


# ── staleness ───────────────────────────────────────────────────────────────
def test_cancelling_an_order_after_the_fact_was_built_is_caught_by_verify(db_session):
    """The whole reason the refresh is trailing rather than incremental."""
    r = _restaurant(db_session, "Stale")
    a, = _menu(db_session, r.id, ["Pilau"])
    when = dt.datetime(2026, 8, 12, 9, 0)
    o = _order(db_session, r.id, when, [(a, 1, 5000)])
    _order(db_session, r.id, when + dt.timedelta(days=1), [(a, 1, 1000)])
    days = [dt.date(2026, 8, d) for d in (12, 13, 14)]
    rollup.rebuild_days(db_session, r.id, days)

    # The window must SEAL 12 Aug, not leave it as the partial head day — a
    # partial day is answered live, so a stale fact for it would never be read
    # and this test would pass while proving nothing. 11 Aug 12:00 UTC is inside
    # 11 Aug EAT, which makes 12-14 Aug the sealed run.
    start, end = dt.datetime(2026, 8, 11, 12, 0), dt.datetime(2026, 8, 14, 22, 0)
    assert rollup._whole_day_span(start, end) == (dt.date(2026, 8, 12), dt.date(2026, 8, 14))
    assert rollup.verify(db_session, r.id, start, end)["status"] == "clean"

    o.status = models.OrderStatus.CANCELLED
    db_session.commit()

    drifted = rollup.verify(db_session, r.id, start, end)
    assert drifted["status"] == "mismatch"
    assert drifted["revenue_drift_kes"] == 50.0    # the cancelled order, still in the fact

    rollup.rebuild_days(db_session, r.id, days)
    assert rollup.verify(db_session, r.id, start, end)["status"] == "clean"


def test_rebuild_removes_an_item_row_that_no_longer_has_sales(db_session):
    """Item facts are deleted and rewritten, not upserted. An upsert-only path
    would leave a stale row claiming sales that were since cancelled."""
    r = _restaurant(db_session, "Removed")
    a, b = _menu(db_session, r.id, ["Samosa", "Kachumbari"])
    when = dt.datetime(2026, 9, 2, 9, 0)
    o = _order(db_session, r.id, when, [(a, 5, 200)])
    _order(db_session, r.id, when, [(b, 1, 900)])
    day = [dt.date(2026, 9, 2)]
    rollup.rebuild_days(db_session, r.id, day)
    assert db_session.query(models.DailyItemSalesFact).filter(
        models.DailyItemSalesFact.restaurant_id == r.id).count() == 2

    o.status = models.OrderStatus.CANCELLED
    db_session.commit()
    rollup.rebuild_days(db_session, r.id, day)

    remaining = db_session.query(models.DailyItemSalesFact).filter(
        models.DailyItemSalesFact.restaurant_id == r.id).all()
    assert len(remaining) == 1
    assert remaining[0].menu_item_id == b.id


# ── determinism ─────────────────────────────────────────────────────────────
def test_top_items_breaks_ties_by_name_so_the_report_is_stable(db_session):
    """Two items on identical quantity must always come back in the same order.

    Found by diffing 60 random windows against the rollup: ties were ordered
    arbitrarily, and at the limit boundary that changed WHICH item appeared.
    The live query disagreed with itself between runs.
    """
    r = _restaurant(db_session, "Ties")
    items = _menu(db_session, r.id, ["Zanzibar", "Athi", "Meru", "Bungoma"])
    when = dt.datetime(2026, 9, 5, 9, 0)
    for mi in items:
        _order(db_session, r.id, when, [(mi, 4, 1000)])   # all equal quantity
    rollup.rebuild_days(db_session, r.id, [dt.date(2026, 9, 5)])

    start, end = when - dt.timedelta(hours=6), when + dt.timedelta(hours=6)
    names = [x["name"] for x in rollup.top_items(db_session, r.id, start, end, limit=3)]
    assert names == ["Athi", "Bungoma", "Meru"]
    assert names == [x["name"] for x in _top_items_live(db_session, r.id, start, end, limit=3)]
