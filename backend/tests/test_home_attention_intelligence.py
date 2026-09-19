"""
The Home page must tell the owner what needs attention — they should not have
to ask. That is the whole split: Home is the system talking, the OS page is the
owner talking.

Before this, _attention_cards was two hardcoded queries (low stock, pending
purchase orders). Nothing ranked, nothing cross-domain, no recommendations —
so the pricing, menu, labour and supply-chain agents' work never reached the
page the owner actually opens.
"""
from __future__ import annotations

import datetime
import random

import pytest

import models
from routers.overview import (
    _attention_cards,
    _card_key,
    _decision_cards,
    _operational_cards,
)


@pytest.fixture
def restaurant(db_session):
    t = models.Tenant(name="Vibanda Village")
    db_session.add(t); db_session.flush()
    r = models.Restaurant(tenant_id=t.id, name="Vibanda Village", address="Nairobi")
    db_session.add(r); db_session.flush()

    items = []
    for name, price, cost in [
        ("Nyama Choma", 65000, 26000),
        ("Grilled Chicken", 75000, 52000),   # thin margin -> pricing advice
        ("Pilau Beef", 45000, 18000),
    ]:
        m = models.MenuItem(restaurant_id=r.id, name=name, price=price,
                            cost_price=cost, category="Food", is_available=True)
        db_session.add(m); items.append(m)
    db_session.flush()

    db_session.add(models.InventoryItem(
        restaurant_id=r.id, item_name="Beef", quantity=1.0, unit="kg",
        low_stock_threshold=5, cost_per_unit_cents=50000))
    db_session.add(models.InventoryItem(
        restaurant_id=r.id, item_name="Rice", quantity=40.0, unit="kg",
        low_stock_threshold=5, cost_per_unit_cents=20000))
    db_session.flush()

    rng = random.Random(7)
    now = datetime.datetime.utcnow()
    for day in range(30):
        for _ in range(rng.randint(6, 12)):
            it = rng.choice(items)
            o = models.Order(restaurant_id=r.id, total=it.price, is_paid=True,
                             status=models.OrderStatus.SERVED,
                             created_at=now - datetime.timedelta(days=day))
            db_session.add(o); db_session.flush()
            db_session.add(models.OrderItem(order_id=o.id, menu_item_id=it.id,
                                            quantity=1, unit_price=it.price))
    db_session.commit()
    return t, r


def test_home_surfaces_ranked_recommendations_not_just_alerts(db_session, restaurant):
    tenant, r = restaurant
    cards = _attention_cards(db_session, r.id, tenant.id)

    ranked = [c for c in cards if c.get("priority_score") is not None]
    assert ranked, (
        "Home showed no ranked recommendations — the owner would have to go and "
        "ask the OS page, which is the problem this page exists to solve"
    )
    domains = {c["domain"] for c in ranked}
    assert domains - {"Stock"}, f"only stock advice surfaced: {domains}"


def test_ranked_cards_are_ordered_best_first(db_session, restaurant):
    tenant, r = restaurant
    ranked = [c["priority_score"] for c in _attention_cards(db_session, r.id, tenant.id)
              if c.get("priority_score") is not None]
    assert ranked == sorted(ranked, reverse=True), (
        f"the most valuable advice is not first: {ranked}"
    )


def test_operational_alerts_come_before_recommendations(db_session, restaurant):
    """A stockout is happening; a pricing change is a good idea. Order matters."""
    tenant, r = restaurant
    cards = _attention_cards(db_session, r.id, tenant.id)
    kinds = [c.get("priority_score") is None for c in cards]
    assert kinds == sorted(kinds, reverse=True), (
        "an operational alert appeared below a recommendation"
    )


def test_ai_advice_does_not_restate_an_operational_alert(db_session, restaurant):
    """'Beef is running low' and 'Reorder Beef soon' are one problem."""
    tenant, r = restaurant
    cards = _attention_cards(db_session, r.id, tenant.id)
    stock_cards = [c["title"].lower() for c in cards if c["domain"] == "Stock"]
    beef = [t for t in stock_cards if "beef" in t]
    assert len(beef) <= 1, f"Beef surfaced {len(beef)} times: {beef}"


def test_quantified_advice_carries_its_money(db_session, restaurant):
    tenant, r = restaurant
    ranked = [c for c in _attention_cards(db_session, r.id, tenant.id)
              if c.get("priority_score") is not None]
    assert any(c["impact"] for c in ranked), (
        "no recommendation showed its monetary impact — the owner cannot "
        "tell a KSh 200 idea from a KSh 20,000 one"
    )


def test_card_ids_are_stable_across_calls(db_session, restaurant):
    """The owner's dismissals key on these ids.

    Keying on rank would resurrect a dismissed card as soon as something else
    outranked it.
    """
    tenant, r = restaurant
    first = [c["id"] for c in _attention_cards(db_session, r.id, tenant.id)]
    second = [c["id"] for c in _attention_cards(db_session, r.id, tenant.id)]
    assert first == second


def test_card_id_tracks_the_advice_not_its_position():
    assert _card_key("pricing", "Raise X to 650") == _card_key("pricing", "Raise X to 650")
    assert _card_key("pricing", "Raise X to 650") != _card_key("pricing", "Raise X to 700")


def test_dismissed_cards_stay_dismissed(db_session, restaurant):
    tenant, r = restaurant
    cards = _attention_cards(db_session, r.id, tenant.id)
    target = cards[0]["id"]
    db_session.add(models.AttentionDecision(
        tenant_id=tenant.id, card_key=target, decision="rejected"))
    db_session.commit()

    after = [c["id"] for c in _attention_cards(db_session, r.id, tenant.id)]
    assert target not in after


def test_home_still_warns_when_the_ai_layer_fails(db_session, restaurant, monkeypatch):
    """Home must render. A failing agent degrades to the operational warnings."""
    import routers.overview as ov

    def boom(*a, **k):
        raise RuntimeError("pricing agent exploded")

    monkeypatch.setattr(ov, "_decision_cards", boom)
    cards = ov._attention_cards(db_session, r_id := restaurant[1].id, restaurant[0].id)
    assert any("beef" in c["title"].lower() for c in cards), (
        "the stockout warning vanished when an agent failed"
    )
    assert all(c.get("priority_score") is None for c in cards)


def test_a_new_restaurant_gets_an_empty_list_not_an_error(db_session):
    t = models.Tenant(name="Brand New")
    db_session.add(t); db_session.flush()
    r = models.Restaurant(tenant_id=t.id, name="Brand New", address="x")
    db_session.add(r); db_session.commit()
    assert _attention_cards(db_session, r.id, t.id) == []
