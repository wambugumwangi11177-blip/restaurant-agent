"""Theft, variance, cash shortfalls and missing cost data must reach Home.

All four detectors were built, tested and scheduled, and reached nobody: the
only screens that displayed them are on the dashboard this owner does not use,
and ai/decisions/adapters.py registered six sources, none of them these. The
owner's single most expensive blind spot was computed every two hours and
thrown away.

These tests assert on GET /overview/today — the page the owner actually opens.
Asserting that compute_fraud_report() returns a flag would have passed against
the broken version, because it always did.
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
    db.add(models.Tenant(id=900, name="Loss tenant"))
    db.flush()
    db.add(models.Restaurant(id=901, tenant_id=900, name="Loss test"))
    db.flush()
    user = models.User(tenant_id=900, active_restaurant_id=901,
                       email="loss-owner@example.com", hashed_password="unused",
                       role=models.Role.ADMIN)
    db.add(user)
    db.commit()
    token = auth.create_access_token({"sub": user.email})
    return user, {"Authorization": f"Bearer {token}"}


def _feed(client, headers) -> dict:
    res = client.get("/api/v1/overview/today", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _titles(feed) -> list[str]:
    return [c["title"] for c in feed["attention"]]


def _domains(feed) -> list[str]:
    return [c["domain"] for c in feed["attention"]]


# ── Stock variance ───────────────────────────────────────────────────────────

def _stocked_item(db, rid, name="Beef", cost_cents=50000):
    item = models.InventoryItem(restaurant_id=rid, item_name=name, quantity=100,
                                unit="kg", low_stock_threshold=5,
                                cost_per_unit_cents=cost_cents)
    db.add(item)
    db.commit()
    return item


def test_a_usage_variance_appears_on_home(client, db_session, owner):
    """Recipes say 10kg left stock; 30kg actually did. That is the shrinkage
    signal directive 016 exists for, and Home never showed it."""
    _, headers = owner
    item = _stocked_item(db_session, 901)
    dish = models.MenuItem(restaurant_id=901, name="Nyama Choma", price=80000,
                           cost_price=30000, category="Grill")
    db_session.add(dish)
    db_session.flush()
    db_session.add(models.MenuIngredient(menu_item_id=dish.id,
                                         inventory_item_id=item.id, quantity_per_serving=1.0))
    order = models.Order(restaurant_id=901, total=800000, is_paid=True,
                         status=models.OrderStatus.SERVED,
                         created_at=utcnow() - timedelta(hours=2))
    db_session.add(order)
    db_session.flush()
    db_session.add(models.OrderItem(order_id=order.id, menu_item_id=dish.id,
                                    quantity=10, unit_price=80000))
    # 30kg actually moved out against a 10kg recipe expectation.
    db_session.add(models.StockMovement(
        inventory_item_id=item.id, movement_type=models.StockMovementType.OUT,
        quantity=30, reason="sale", created_at=utcnow() - timedelta(hours=1)))
    db_session.commit()

    feed = _feed(client, headers)
    assert any("Beef" in t for t in _titles(feed)), _titles(feed)
    assert "Loss" in _domains(feed)


def test_a_variance_card_is_not_suppressed_by_a_low_stock_card(client, db_session, owner):
    """Running low and being stolen are different problems about one ingredient.
    The dedupe drops a Stock card naming an already-low item; a Loss card must
    survive it."""
    _, headers = owner
    item = models.InventoryItem(restaurant_id=901, item_name="Beef", quantity=1,
                                unit="kg", low_stock_threshold=10,
                                cost_per_unit_cents=50000)
    db_session.add(item)
    dish = models.MenuItem(restaurant_id=901, name="Nyama Choma", price=80000,
                           cost_price=30000, category="Grill")
    db_session.add(dish)
    db_session.flush()
    db_session.add(models.MenuIngredient(menu_item_id=dish.id,
                                         inventory_item_id=item.id, quantity_per_serving=1.0))
    order = models.Order(restaurant_id=901, total=800000, is_paid=True,
                         status=models.OrderStatus.SERVED,
                         created_at=utcnow() - timedelta(hours=2))
    db_session.add(order)
    db_session.flush()
    db_session.add(models.OrderItem(order_id=order.id, menu_item_id=dish.id,
                                    quantity=10, unit_price=80000))
    db_session.add(models.StockMovement(
        inventory_item_id=item.id, movement_type=models.StockMovementType.OUT,
        quantity=30, reason="sale", created_at=utcnow() - timedelta(hours=1)))
    db_session.commit()

    feed = _feed(client, headers)
    domains = _domains(feed)
    assert "Stock" in domains, "the low-stock warning must still be there"
    assert "Loss" in domains, "the variance must not be swallowed by it"


# ── Cash ─────────────────────────────────────────────────────────────────────

def test_a_cash_shortfall_appears_on_home_with_its_money(client, db_session, owner):
    user, headers = owner
    db_session.add(models.CashDrawerCount(
        restaurant_id=901, expected_amount_cents=1_000_000,
        counted_amount_cents=600_000, counted_by_user_id=user.id,
        window_start=utcnow() - timedelta(hours=9),
        window_end=utcnow() - timedelta(hours=1),
        counted_at=utcnow() - timedelta(hours=1)))
    db_session.commit()

    feed = _feed(client, headers)
    card = next((c for c in feed["attention"] if c["domain"] == "Loss"), None)
    assert card is not None, _titles(feed)
    assert "drawer" in card["title"].lower()
    # KES 4,000 short in 24h is the observed figure; the card carries a monthly
    # projection so it can outrank a small price change.
    assert card["impact"], "a cash shortfall must carry its money"


# ── Data quality ─────────────────────────────────────────────────────────────

def test_missing_cost_prices_appear_on_home(client, db_session, owner):
    """An item with no cost can never be flagged as losing money, so the gap
    itself is the finding."""
    _, headers = owner
    db_session.add(models.MenuItem(restaurant_id=901, name="Uncosted Pilau",
                                   price=50000, cost_price=0, category="Main"))
    db_session.commit()

    feed = _feed(client, headers)
    assert any("cost price" in t.lower() for t in _titles(feed)), _titles(feed)


# ── Registration ─────────────────────────────────────────────────────────────

def test_every_detector_the_product_claims_is_registered():
    """Adding a detector without registering it here is exactly how four of
    them stayed invisible. This fails when that happens again."""
    from ai.decisions.adapters import _ADAPTERS
    expected = {
        "fraud", "stock_custody", "cash_reconciliation", "data_quality",
        "pricing", "inventory", "supply_chain", "menu", "labor", "marketing",
    }
    assert set(_ADAPTERS) == expected


def test_loss_prevention_is_ranked_not_appended(db_session, owner):
    """Loss decisions go through the same ranking as everything else — they are
    not pinned to the top, and a quantified one must be able to outrank a
    small pricing change on its own merits."""
    from ai.decisions import get_ranked_decisions
    user, _ = owner
    db_session.add(models.CashDrawerCount(
        restaurant_id=901, expected_amount_cents=2_000_000,
        counted_amount_cents=1_000_000, counted_by_user_id=user.id,
        window_start=utcnow() - timedelta(hours=9),
        window_end=utcnow() - timedelta(hours=1),
        counted_at=utcnow() - timedelta(hours=1)))
    db_session.commit()

    ranked = get_ranked_decisions(db_session, 901)["decisions"]
    cash = next(d for d in ranked if d["agent"] == "cash_reconciliation")
    assert cash["quantified"] is True
    assert cash["impact_cents_month"] > 0
    assert cash["rank"] == 1, "KES 10,000 short a day should lead the page"


def test_an_uncosted_variance_is_reported_without_a_fake_figure(db_session, owner):
    """No cost price means no shilling value. Saying zero would rank a real
    theft at the bottom of the list."""
    from ai.decisions.adapters import from_stock_custody
    item = models.InventoryItem(restaurant_id=901, item_name="Unpriced Rice",
                                quantity=100, unit="kg", low_stock_threshold=5,
                                cost_per_unit_cents=0)
    db_session.add(item)
    dish = models.MenuItem(restaurant_id=901, name="Rice Bowl", price=30000,
                           cost_price=10000, category="Main")
    db_session.add(dish)
    db_session.flush()
    db_session.add(models.MenuIngredient(menu_item_id=dish.id,
                                         inventory_item_id=item.id, quantity_per_serving=1.0))
    order = models.Order(restaurant_id=901, total=300000, is_paid=True,
                         status=models.OrderStatus.SERVED,
                         created_at=utcnow() - timedelta(hours=2))
    db_session.add(order)
    db_session.flush()
    db_session.add(models.OrderItem(order_id=order.id, menu_item_id=dish.id,
                                    quantity=10, unit_price=30000))
    db_session.add(models.StockMovement(
        inventory_item_id=item.id, movement_type=models.StockMovementType.OUT,
        quantity=40, reason="sale", created_at=utcnow() - timedelta(hours=1)))
    db_session.commit()

    decisions = from_stock_custody(db_session, 901)
    assert decisions, "a 300% variance must still be reported"
    assert decisions[0].impact_cents_month is None
    assert "cannot be stated" in decisions[0].rationale
