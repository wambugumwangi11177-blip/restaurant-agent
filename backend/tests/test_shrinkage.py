"""
Shrinkage detection — physical stock counts vs the theoretical usage
stock_ledger.py already tracks.

Directive 007 flagged this as the natural next piece once recipes existed:
theoretical usage (recipes x orders sold) was trackable, but nothing compared
it against what was physically on the shelf, so shrinkage — food walking out
the back, over-portioning, spillage, theft — was invisible.

These tests pin two things: that a count correctly reconciles the system to
reality (and the reconciling StockMovement lands in the existing ledger, not a
separate one), and that the aggregate report correctly separates loss from
overage and flags items nobody has ever counted.
"""

import auth
import models
import stock_ledger


def _owner(db_session, suffix):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"count{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN,
        token_version=0,
    )
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add_all([user, restaurant])
    db_session.commit()
    return auth.create_access_token({"sub": user.email, "ver": 0}), restaurant.id


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _ingredient(db_session, restaurant_id, name, qty, cost_per_unit=100.0):
    inv = models.InventoryItem(
        restaurant_id=restaurant_id, item_name=name, quantity=qty, unit="kg",
        cost_per_unit=cost_per_unit, low_stock_threshold=1,
    )
    db_session.add(inv)
    db_session.commit()
    return inv.id


# ── Recording a count ────────────────────────────────────────────────────────

def test_count_reconciles_system_quantity_to_the_physical_count(client, db_session):
    token, rid = _owner(db_session, "reconcile")
    chicken = _ingredient(db_session, rid, "Chicken", 10.0)

    r = client.post(f"/inventory/{chicken}/count", headers=_hdr(token),
                    json={"counted_quantity": 7.0, "notes": "Friday close count"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["expected_quantity"] == 10.0
    assert body["counted_quantity"] == 7.0
    assert body["variance"] == -3.0

    db_session.expire_all()
    assert db_session.get(models.InventoryItem, chicken).quantity == 7.0


def test_shortfall_writes_a_reconciling_movement_in_the_existing_ledger(client, db_session):
    """
    A count that's never reconciled would leave InventoryItem.quantity
    permanently wrong until the next one — every other analytic reads that
    field, so the movement has to land in the SAME ledger stock_ledger.py and
    /adjust already write to, not a separate one only this feature knows about.
    """
    token, rid = _owner(db_session, "movement")
    chicken = _ingredient(db_session, rid, "Chicken", 10.0)

    client.post(f"/inventory/{chicken}/count", headers=_hdr(token),
               json={"counted_quantity": 6.0})

    movement = db_session.query(models.StockMovement).filter(
        models.StockMovement.inventory_item_id == chicken
    ).one()
    assert movement.movement_type == models.StockMovementType.ADJUST
    assert movement.quantity == 4.0
    assert movement.reason.startswith("stock_count:")


def test_exact_match_writes_no_movement(client, db_session):
    """A count that confirms the system was right shouldn't add ledger noise."""
    token, rid = _owner(db_session, "exact")
    chicken = _ingredient(db_session, rid, "Chicken", 10.0)

    r = client.post(f"/inventory/{chicken}/count", headers=_hdr(token),
                    json={"counted_quantity": 10.0})
    assert r.json()["variance"] == 0.0
    assert db_session.query(models.StockMovement).count() == 0


def test_overage_is_recorded_not_just_shortfall(client, db_session):
    """More on the shelf than expected is a real outcome — a miscounted
    delivery, or a correction — and must be recorded, not silently dropped."""
    token, rid = _owner(db_session, "over")
    chicken = _ingredient(db_session, rid, "Chicken", 10.0)

    r = client.post(f"/inventory/{chicken}/count", headers=_hdr(token),
                    json={"counted_quantity": 13.0})
    assert r.json()["variance"] == 3.0
    db_session.expire_all()
    assert db_session.get(models.InventoryItem, chicken).quantity == 13.0


def test_count_history_is_queryable_per_item(client, db_session):
    token, rid = _owner(db_session, "history")
    chicken = _ingredient(db_session, rid, "Chicken", 10.0)

    client.post(f"/inventory/{chicken}/count", headers=_hdr(token), json={"counted_quantity": 8.0})
    client.post(f"/inventory/{chicken}/count", headers=_hdr(token), json={"counted_quantity": 7.0})

    history = client.get(f"/inventory/{chicken}/counts", headers=_hdr(token)).json()
    assert len(history) == 2
    assert history[0]["counted_quantity"] == 7.0   # most recent first


def test_cannot_count_another_restaurants_item(client, db_session):
    token_a, _ = _owner(db_session, "ca")
    _, rid_b = _owner(db_session, "cb")
    theirs = _ingredient(db_session, rid_b, "Theirs", 5.0)

    r = client.post(f"/inventory/{theirs}/count", headers=_hdr(token_a),
                    json={"counted_quantity": 1.0})
    assert r.status_code == 404


def test_counting_is_not_admin_only(client, db_session):
    """Physical counting is floor work, like receiving stock — staff do it."""
    token, rid = _owner(db_session, "staffcount")
    tenant_id = db_session.get(models.Restaurant, rid).tenant_id
    staff = models.User(
        tenant_id=tenant_id, email="floor@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF, token_version=0,
    )
    db_session.add(staff)
    db_session.commit()
    staff_token = auth.create_access_token({"sub": staff.email, "ver": 0})

    chicken = _ingredient(db_session, rid, "Chicken", 10.0)
    r = client.post(f"/inventory/{chicken}/count", headers=_hdr(staff_token),
                    json={"counted_quantity": 9.0})
    assert r.status_code == 200


# ── The report ───────────────────────────────────────────────────────────────

def test_shrinkage_report_separates_loss_from_overage_by_value(client, db_session):
    from ai.shrinkage import get_shrinkage_report

    token, rid = _owner(db_session, "report")
    # KES 100/kg. Lost 3kg -> KES 300 -> 30000 cents.
    chicken = _ingredient(db_session, rid, "Chicken", 10.0, cost_per_unit=100.0)
    # KES 50/kg. Gained 2kg -> KES 100 -> 10000 cents.
    rice = _ingredient(db_session, rid, "Rice", 5.0, cost_per_unit=50.0)

    client.post(f"/inventory/{chicken}/count", headers=_hdr(token), json={"counted_quantity": 7.0})
    client.post(f"/inventory/{rice}/count", headers=_hdr(token), json={"counted_quantity": 7.0})

    report = get_shrinkage_report(db_session, rid, days=90)
    assert report["summary"]["total_shrinkage_value_cents"] == 30000
    assert report["summary"]["total_overage_value_cents"] == 10000
    assert report["summary"]["items_counted"] == 2

    by_name = {i["item_name"]: i for i in report["items"]}
    assert by_name["Chicken"]["shrinkage_value_cents"] == 30000
    assert by_name["Chicken"]["overage_value_cents"] == 0
    assert by_name["Rice"]["overage_value_cents"] == 10000


def test_multiple_counts_on_the_same_item_accumulate(client, db_session):
    """A pattern of loss across counts is the actual signal, not one bad night."""
    from ai.shrinkage import get_shrinkage_report

    token, rid = _owner(db_session, "accumulate")
    chicken = _ingredient(db_session, rid, "Chicken", 10.0, cost_per_unit=100.0)

    client.post(f"/inventory/{chicken}/count", headers=_hdr(token), json={"counted_quantity": 8.0})  # -2
    # receive more, then lose again
    client.post(f"/inventory/{chicken}/receive", headers=_hdr(token), json={"quantity": 10.0})
    client.post(f"/inventory/{chicken}/count", headers=_hdr(token), json={"counted_quantity": 16.0})  # -2

    report = get_shrinkage_report(db_session, rid, days=90)
    chicken_report = report["items"][0]
    assert chicken_report["count_events"] == 2
    assert chicken_report["shrinkage_qty"] == 4.0
    assert chicken_report["shrinkage_value_cents"] == 40000


def test_items_never_counted_are_flagged(client, db_session):
    from ai.shrinkage import get_shrinkage_report

    token, rid = _owner(db_session, "never")
    counted = _ingredient(db_session, rid, "Counted", 10.0)
    uncounted = _ingredient(db_session, rid, "Uncounted", 5.0)

    client.post(f"/inventory/{counted}/count", headers=_hdr(token), json={"counted_quantity": 9.0})

    report = get_shrinkage_report(db_session, rid, days=90)
    assert report["summary"]["items_never_counted"] == 1
    assert [i["item_name"] for i in report["never_counted"]] == ["Uncounted"]


def test_report_with_zero_counts_flags_everything_as_never_counted(db_session):
    from ai.shrinkage import get_shrinkage_report

    tenant = models.Tenant(name="Empty")
    db_session.add(tenant); db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="R", address="x")
    db_session.add(restaurant); db_session.commit()
    _ingredient(db_session, restaurant.id, "Untouched", 3.0)

    report = get_shrinkage_report(db_session, restaurant.id, days=90)
    assert report["summary"]["items_counted"] == 0
    assert report["summary"]["items_never_counted"] == 1
    assert report["items"] == []


def test_counts_outside_the_window_are_excluded(client, db_session):
    from datetime import timedelta
    from ai.shrinkage import get_shrinkage_report
    from time_utils import utcnow

    token, rid = _owner(db_session, "window")
    chicken = _ingredient(db_session, rid, "Chicken", 10.0, cost_per_unit=100.0)
    client.post(f"/inventory/{chicken}/count", headers=_hdr(token), json={"counted_quantity": 5.0})

    # Push the count outside a 7-day window.
    count = db_session.query(models.StockCount).one()
    count.created_at = utcnow() - timedelta(days=30)
    db_session.commit()

    report = get_shrinkage_report(db_session, rid, days=7)
    assert report["summary"]["items_counted"] == 0
    assert report["items"] == []


def test_shrinkage_endpoint_is_gated_by_billing(client, db_session):
    """
    /ai/shrinkage lives on the /ai router, which is gated by
    require_active_subscription. Counting itself (POST /inventory/.../count)
    is operational and must NOT be gated — only the report is "the analysis".
    """
    from datetime import timedelta
    from routers import billing
    from time_utils import utcnow

    token, rid = _owner(db_session, "gate")
    sub = db_session.query(models.Subscription).filter(
        models.Subscription.tenant_id == db_session.get(models.Restaurant, rid).tenant_id
    ).first()
    if sub is None:
        sub = models.Subscription(
            tenant_id=db_session.get(models.Restaurant, rid).tenant_id,
            plan="free", status=billing.STATUS_TRIALING, provider="manual",
        )
        db_session.add(sub)
    sub.current_period_end = utcnow() - timedelta(days=billing.GRACE_DAYS + 5)
    db_session.commit()

    chicken = _ingredient(db_session, rid, "Chicken", 10.0)
    # Counting still works — it's operational.
    assert client.post(f"/inventory/{chicken}/count", headers=_hdr(token),
                       json={"counted_quantity": 9.0}).status_code == 200
    # The report is gated.
    assert client.get("/api/v1/ai/shrinkage", headers=_hdr(token)).status_code == 402
