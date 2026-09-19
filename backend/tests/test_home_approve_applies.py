"""Approving on Home must change the business, not just hide the card.

The endpoint wrote one AttentionDecision row and returned. It never called
approve_recommendation() (the only code that changes a price) or
approve_and_send() (the only code that sends a purchase order), and the row's
sole other use was to filter the card out of the next feed. Approving a
KES 40,000/month price change and dismissing it had identical effects.

tests/test_overview_scope.py:104 asserted that outcome as correct behaviour —
"Recording advice never changes operational stock" — which is true of a stock
warning and was being applied to everything.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

import auth
import models
from time_utils import utcnow


@pytest.fixture
def owner(db_session):
    db = db_session
    db.add(models.Tenant(id=1000, name="Approve tenant"))
    db.flush()
    db.add(models.Restaurant(id=1001, tenant_id=1000, name="Approve test"))
    db.flush()
    user = models.User(tenant_id=1000, active_restaurant_id=1001,
                       email="approve-owner@example.com", hashed_password="unused",
                       role=models.Role.ADMIN)
    db.add(user)
    db.commit()
    return user, {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email})}"}


def _feed(client, headers):
    res = client.get("/api/v1/overview/today", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _decide(client, headers, card_id, decision):
    res = client.post(f"/api/v1/overview/attention/{card_id}/decision",
                      json={"decision": decision}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _thin_margin_item(db, rid):
    """An item below the 40% margin floor with enough velocity to be repriced."""
    item = models.MenuItem(restaurant_id=rid, name="Thin Margin Fish",
                           price=10000, cost_price=8000, category="Main")
    db.add(item)
    db.flush()
    for day in range(1, 25):
        order = models.Order(restaurant_id=rid, total=30000, is_paid=True,
                             status=models.OrderStatus.SERVED,
                             created_at=utcnow() - timedelta(days=day))
        db.add(order)
        db.flush()
        db.add(models.OrderItem(order_id=order.id, menu_item_id=item.id,
                                quantity=3, unit_price=item.price))
    db.commit()
    return item


# ── Pricing ──────────────────────────────────────────────────────────────────

def test_approving_a_pricing_card_changes_the_menu_price(client, db_session, owner):
    _, headers = owner
    item = _thin_margin_item(db_session, 1001)
    original = item.price

    feed = _feed(client, headers)
    card = next((c for c in feed["attention"] if c.get("agent") == "pricing_intelligence"), None)
    assert card is not None, [c["title"] for c in feed["attention"]]
    assert card["applies"] is True
    assert card["action_label"] == "Approve"

    body = _decide(client, headers, card["id"], "approved")
    assert body["applied"] is True
    assert body["message"]

    db_session.expire_all()
    updated = db_session.query(models.MenuItem).filter_by(id=item.id).one()
    assert updated.price != original, "approving must move the price"


def test_rejecting_a_pricing_card_leaves_the_price_alone(client, db_session, owner):
    _, headers = owner
    item = _thin_margin_item(db_session, 1001)
    original = item.price

    feed = _feed(client, headers)
    card = next(c for c in feed["attention"] if c.get("agent") == "pricing_intelligence")
    _decide(client, headers, card["id"], "rejected")

    db_session.expire_all()
    assert db_session.query(models.MenuItem).filter_by(id=item.id).one().price == original


def test_a_rejected_recommendation_stops_being_offered(client, db_session, owner):
    _, headers = owner
    _thin_margin_item(db_session, 1001)
    card = next(c for c in _feed(client, headers)["attention"]
                if c.get("agent") == "pricing_intelligence")
    _decide(client, headers, card["id"], "rejected")

    again = [c["id"] for c in _feed(client, headers)["attention"]]
    assert card["id"] not in again


# ── Purchase orders ──────────────────────────────────────────────────────────

def test_approving_the_purchase_order_card_sends_the_orders(client, db_session, owner):
    """The card said "review and approve the pending purchase orders" and led
    nowhere — Vibanda has no purchasing screen."""
    _, headers = owner
    supplier = models.Supplier(restaurant_id=1001, name="Mama Njeri Produce")
    item = models.InventoryItem(restaurant_id=1001, item_name="Tomatoes", quantity=5,
                                unit="kg", low_stock_threshold=20,
                                cost_per_unit_cents=15000)
    db_session.add_all([supplier, item])
    db_session.flush()
    po = models.PurchaseOrder(restaurant_id=1001, supplier_id=supplier.id,
                              inventory_item_id=item.id, quantity_ordered=30,
                              unit="kg", status="PENDING")
    db_session.add(po)
    db_session.commit()

    feed = _feed(client, headers)
    card = next(c for c in feed["attention"] if c.get("agent") == "reorder")
    assert card["applies"] is True
    assert card["purchase_order_ids"] == [po.id]

    body = _decide(client, headers, card["id"], "approved")
    assert body["applied"] is True

    db_session.expire_all()
    assert db_session.query(models.PurchaseOrder).filter_by(id=po.id).one().status == "SENT"


def test_rejecting_the_purchase_order_card_does_not_cancel_the_orders(client, db_session, owner):
    """Dismissing a card is not cancelling an order with a supplier on the
    other end."""
    _, headers = owner
    supplier = models.Supplier(restaurant_id=1001, name="Mama Njeri Produce")
    item = models.InventoryItem(restaurant_id=1001, item_name="Tomatoes", quantity=5,
                                unit="kg", low_stock_threshold=20,
                                cost_per_unit_cents=15000)
    db_session.add_all([supplier, item])
    db_session.flush()
    po = models.PurchaseOrder(restaurant_id=1001, supplier_id=supplier.id,
                              inventory_item_id=item.id, quantity_ordered=30,
                              unit="kg", status="PENDING")
    db_session.add(po)
    db_session.commit()

    card = next(c for c in _feed(client, headers)["attention"] if c.get("agent") == "reorder")
    body = _decide(client, headers, card["id"], "rejected")

    db_session.expire_all()
    assert db_session.query(models.PurchaseOrder).filter_by(id=po.id).one().status == "PENDING"
    assert body["applied"] is False
    assert "left pending" in body["message"]


# ── Honesty of the label ─────────────────────────────────────────────────────

def test_an_advisory_card_does_not_claim_to_approve_anything(client, db_session, owner):
    """"Check Beef usage against the recipes" is carried out by a person in a
    store room. The button must not say Approve."""
    _, headers = owner
    db_session.add(models.InventoryItem(
        restaurant_id=1001, item_name="Beef", quantity=1, unit="kg",
        low_stock_threshold=10, cost_per_unit_cents=50000))
    db_session.commit()

    feed = _feed(client, headers)
    stock_card = next(c for c in feed["attention"] if c["domain"] == "Stock")
    assert stock_card["applies"] is False
    assert stock_card["action_label"] == "Mark as done"

    body = _decide(client, headers, stock_card["id"], "approved")
    assert body["applied"] is False


def test_every_card_declares_what_its_button_does(client, db_session, owner):
    """A missing flag would let the frontend fall back to "Approve" on a card
    that cannot be approved — the exact defect this replaced."""
    _, headers = owner
    _thin_margin_item(db_session, 1001)
    db_session.add(models.InventoryItem(
        restaurant_id=1001, item_name="Beef", quantity=1, unit="kg",
        low_stock_threshold=10, cost_per_unit_cents=50000))
    db_session.commit()

    for card in _feed(client, headers)["attention"]:
        assert "applies" in card, card["title"]
        assert card.get("action_label"), card["title"]
        assert card.get("apply_hint"), card["title"]


def test_a_decision_is_still_recorded_when_nothing_can_be_applied(client, db_session, owner):
    """Failing to apply must never lose the owner's decision."""
    _, headers = owner
    body = _decide(client, headers, "d-nonexistent", "approved")
    assert body["status"] == "approved"
    assert body["applied"] is False
    row = db_session.query(models.AttentionDecision).filter_by(card_key="d-nonexistent").one()
    assert row.decision == "approved"


# ── The cooldown that deleted its own output ─────────────────────────────────

def test_a_recommendation_survives_repeated_page_loads(db_session, owner):
    """Materializing a recommendation used to suppress it.

    items_on_cooldown_for_restaurant counted PENDING as a cooldown, so:
    read 1 produced a recommendation and stored it PENDING; read 2 saw that row
    as a cooldown, produced nothing, and sync marked it EXPIRED for no longer
    being computed; read 3 produced it again. The card flapped on every other
    page load and the table grew by one dead row per refresh, forever.

    A PENDING recommendation is an open offer, not a past action.
    """
    from ai.pricing.recommendations import (
        get_pricing_intelligence, sync_pending_recommendations,
    )
    _thin_margin_item(db_session, 1001)

    seen = []
    for _ in range(4):
        data = get_pricing_intelligence(db_session, 1001)
        seen.append(len(sync_pending_recommendations(
            db_session, 1001, data.get("recommendations", []))))

    assert seen == [1, 1, 1, 1], f"recommendation flapped across reads: {seen}"
    rows = db_session.query(models.PricingRecommendation).filter_by(restaurant_id=1001).all()
    assert len(rows) == 1, f"one row per refresh leaked: {[(r.id, r.status) for r in rows]}"
    assert rows[0].status == "PENDING"


def test_an_approved_price_is_not_re_recommended_inside_the_cooldown(db_session, owner):
    """The cooldown still does its real job: no churning a price we just moved."""
    from ai.pricing.analysis import items_on_cooldown_for_restaurant
    item = _thin_margin_item(db_session, 1001)
    db_session.add(models.PricingRecommendation(
        restaurant_id=1001, menu_item_id=item.id, recommendation_type="REPRICE",
        status="APPROVED", current_price=10000, suggested_price=13300,
        created_at=utcnow() - timedelta(days=1)))
    db_session.commit()

    assert item.id in items_on_cooldown_for_restaurant(db_session, 1001)


def test_an_expired_recommendation_does_not_hold_the_cooldown(db_session, owner):
    from ai.pricing.analysis import items_on_cooldown_for_restaurant
    item = _thin_margin_item(db_session, 1001)
    db_session.add(models.PricingRecommendation(
        restaurant_id=1001, menu_item_id=item.id, recommendation_type="REPRICE",
        status="EXPIRED", current_price=10000, suggested_price=13300,
        created_at=utcnow() - timedelta(days=1)))
    db_session.commit()

    assert item.id not in items_on_cooldown_for_restaurant(db_session, 1001)
