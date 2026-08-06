"""
Kitchen prep-time capture on KDS status transitions.

Until 2026-08-06 nothing in the running application ever wrote a PrepTime row.
The only writer in the whole codebase was `populate_production.py` — the demo
seeder — so `ai/kds_intelligence.py` (per-station p95/median/std-dev, bottleneck
severity, queue depth, delay-risk scoring, ~12 analytics) read an empty table on
every real restaurant and silently returned `_empty_response()`. The kitchen
module wasn't broken; it was starved.

These tests pin the write path, and specifically the three behaviours that make
the resulting statistics trustworthy:
  • the timer's `station` comes from MenuItem.prep_station, so the per-station
    breakdown is real rather than everything landing in "main";
  • transitions are idempotent — a double-tapped KDS button must not create a
    second row or re-stamp a measurement that was already taken;
  • a kitchen that bumps PENDING -> READY without ever pressing PREP still
    produces a measurement, since otherwise those tickets would contribute
    nothing at all to the kitchen's numbers.
"""

import auth
import models


def _owner(db_session, suffix="k"):
    """An ADMIN user with a restaurant, returning (token, restaurant_id)."""
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"owner{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN,
        token_version=0,
    )
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add_all([user, restaurant])
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return token, restaurant.id


def _menu_item(db_session, restaurant_id, name, station):
    item = models.MenuItem(
        restaurant_id=restaurant_id, name=name, price=1000, cost_price=300,
        category="main", prep_station=station,
    )
    db_session.add(item)
    db_session.commit()
    return item.id


def _place_order(client, token, menu_item_id, qty=1):
    r = client.post(
        "/orders/",
        headers={"Authorization": f"Bearer {token}"},
        json={"items": [{"menu_item_id": menu_item_id, "quantity": qty}]},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _set_status(client, token, order_id, status):
    return client.patch(
        f"/orders/{order_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": status},
    )


# ── The core path ────────────────────────────────────────────────────────────

def test_prep_timer_opens_on_prep_and_closes_on_ready(client, db_session):
    token, rid = _owner(db_session, "core")
    mid = _menu_item(db_session, rid, "Grilled Chicken", "grill")
    order_id = _place_order(client, token, mid)

    # Nothing recorded until the ticket actually reaches the kitchen.
    assert db_session.query(models.PrepTime).count() == 0

    assert _set_status(client, token, order_id, "prep").status_code == 200
    timers = db_session.query(models.PrepTime).all()
    assert len(timers) == 1
    assert timers[0].started_at is not None
    assert timers[0].completed_at is None
    assert timers[0].actual_minutes is None   # still cooking — not yet measurable

    assert _set_status(client, token, order_id, "ready").status_code == 200
    db_session.expire_all()
    timer = db_session.query(models.PrepTime).one()
    assert timer.completed_at is not None
    assert timer.actual_minutes is not None
    assert timer.actual_minutes >= 0


def test_station_comes_from_menu_item_not_default(client, db_session):
    """
    The whole per-station analysis depends on this. If station were left at its
    "main" default, kds_intelligence would report one giant bucket and its
    bottleneck detection — which compares stations against each other — could
    never fire.
    """
    token, rid = _owner(db_session, "station")
    grill = _menu_item(db_session, rid, "Steak", "grill")
    fryer = _menu_item(db_session, rid, "Fries", "fryer")

    for mid in (grill, fryer):
        oid = _place_order(client, token, mid)
        _set_status(client, token, oid, "prep")
        _set_status(client, token, oid, "served")

    stations = sorted(pt.station for pt in db_session.query(models.PrepTime).all())
    assert stations == ["fryer", "grill"]


def test_one_timer_per_order_item(client, db_session):
    """A three-line ticket produces three independently-timed rows."""
    token, rid = _owner(db_session, "multi")
    a = _menu_item(db_session, rid, "Wings", "fryer")
    b = _menu_item(db_session, rid, "Salad", "salad")
    c = _menu_item(db_session, rid, "Mojito", "drinks")

    r = client.post(
        "/orders/",
        headers={"Authorization": f"Bearer {token}"},
        json={"items": [
            {"menu_item_id": a, "quantity": 1},
            {"menu_item_id": b, "quantity": 2},
            {"menu_item_id": c, "quantity": 1},
        ]},
    )
    order_id = r.json()["id"]
    _set_status(client, token, order_id, "prep")

    assert db_session.query(models.PrepTime).count() == 3


# ── Idempotence ──────────────────────────────────────────────────────────────

def test_repeated_prep_transition_does_not_duplicate_timers(client, db_session):
    token, rid = _owner(db_session, "dup")
    mid = _menu_item(db_session, rid, "Burger", "grill")
    order_id = _place_order(client, token, mid)

    for _ in range(4):
        _set_status(client, token, order_id, "prep")

    assert db_session.query(models.PrepTime).count() == 1


def test_repeated_close_does_not_restamp_measurement(client, db_session):
    """
    READY then SERVED both close-eligible. The measurement taken at READY must
    survive — otherwise every prep time would silently become "time until the
    plate was carried out", inflating the kitchen's numbers by the whole
    service window.
    """
    token, rid = _owner(db_session, "restamp")
    mid = _menu_item(db_session, rid, "Pasta", "main")
    order_id = _place_order(client, token, mid)

    _set_status(client, token, order_id, "prep")
    _set_status(client, token, order_id, "ready")
    db_session.expire_all()
    first = db_session.query(models.PrepTime).one().actual_minutes

    _set_status(client, token, order_id, "served")
    db_session.expire_all()
    assert db_session.query(models.PrepTime).one().actual_minutes == first


def test_backwards_bump_does_not_reopen_a_closed_timer(client, db_session):
    token, rid = _owner(db_session, "bump")
    mid = _menu_item(db_session, rid, "Soup", "main")
    order_id = _place_order(client, token, mid)

    _set_status(client, token, order_id, "prep")
    _set_status(client, token, order_id, "ready")
    _set_status(client, token, order_id, "prep")     # kitchen corrects itself
    db_session.expire_all()

    timer = db_session.query(models.PrepTime).one()
    assert timer.completed_at is not None            # stays closed
    assert db_session.query(models.PrepTime).count() == 1


# ── Edge cases that would otherwise lose data ────────────────────────────────

def test_skipping_prep_still_records_a_measurement(client, db_session):
    """
    Plenty of kitchens bump straight from PENDING to READY. Without the
    open-then-close fallback those tickets would contribute nothing, and a busy
    restaurant that never presses PREP would see an empty kitchen dashboard
    while running hundreds of orders a day.
    """
    token, rid = _owner(db_session, "skip")
    mid = _menu_item(db_session, rid, "Toast", "main")
    order_id = _place_order(client, token, mid)

    _set_status(client, token, order_id, "ready")
    db_session.expire_all()

    timer = db_session.query(models.PrepTime).one()
    assert timer.actual_minutes is not None
    assert timer.actual_minutes >= 0


def test_cancelled_order_leaves_timer_open_and_out_of_statistics(client, db_session):
    """
    An abandoned ticket must not be counted as a fast prep. kds_intelligence
    only reads rows with actual_minutes set, so leaving the row open is
    sufficient — and is why no cleanup job is needed.
    """
    token, rid = _owner(db_session, "cancel")
    mid = _menu_item(db_session, rid, "Curry", "main")
    order_id = _place_order(client, token, mid)

    _set_status(client, token, order_id, "prep")
    _set_status(client, token, order_id, "cancelled")
    db_session.expire_all()

    timer = db_session.query(models.PrepTime).one()
    assert timer.completed_at is None
    assert timer.actual_minutes is None


def test_kds_intelligence_reports_real_stations_end_to_end(client, db_session):
    """
    The point of the whole change: with the write path in place, the kitchen
    module stops returning its empty response and produces per-station numbers.
    """
    from ai.kds_intelligence import get_kds_intelligence

    token, rid = _owner(db_session, "e2e")
    grill = _menu_item(db_session, rid, "Ribs", "grill")
    fryer = _menu_item(db_session, rid, "Chips", "fryer")

    for mid in (grill, grill, fryer):
        oid = _place_order(client, token, mid)
        _set_status(client, token, oid, "prep")
        _set_status(client, token, oid, "served")

    result = get_kds_intelligence(db_session, rid)
    stations = {s["station"]: s for s in result["station_performance"]}
    assert set(stations) == {"grill", "fryer"}
    assert stations["grill"]["total_items"] == 2
    assert stations["fryer"]["total_items"] == 1
