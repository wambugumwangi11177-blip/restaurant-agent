"""
Business Knowledge Graph — build + impact traversal.

The graph is the substrate the CEO agent and simulator reason over, so its
edges and its blast-radius math must be exactly right: a supplier's impact must
reach the dishes that depend (critically) on the ingredients it supplies, and
'revenue at risk' must count ONLY the dishes a critical shortage would actually
stop — a garnish going missing doesn't take the dish down.
"""

from datetime import timedelta

import pytest

import models
from time_utils import utcnow
from ai.graph import build_graph, get_impact
from ai.graph.build import node_key
from ai.graph.traverse import downstream, upstream


def _tenant_id(db) -> int:
    tenant = models.Tenant(name="Graph Tenant")
    db.add(tenant)
    db.commit()
    return tenant.id


@pytest.fixture
def wired(db_session):
    """supplier → chicken → {ChickenBurger (critical), Garnished (non-critical)}."""
    db = db_session
    db.add(models.Restaurant(id=1, tenant_id=_tenant_id(db), name="Graph", address="x"))
    db.add_all([
        models.MenuItem(id=1, restaurant_id=1, name="ChickenBurger", price=1000, cost_price=400, category="mains"),
        models.MenuItem(id=2, restaurant_id=1, name="GarnishedDish", price=800, cost_price=300, category="mains"),
    ])
    db.add(models.InventoryItem(id=1, restaurant_id=1, item_name="Chicken",
                                quantity=5.0, unit="kg", low_stock_threshold=10))
    db.add(models.Supplier(id=1, restaurant_id=1, name="Supplier A", reliability_score=80.0, avg_lead_days=2))
    db.commit()
    # chicken is CRITICAL to the burger, a non-critical garnish on the other dish
    db.add_all([
        models.MenuIngredient(menu_item_id=1, inventory_item_id=1, quantity_per_serving=0.2, is_critical=True),
        models.MenuIngredient(menu_item_id=2, inventory_item_id=1, quantity_per_serving=0.01, is_critical=False),
    ])
    # supplier A supplied chicken (a purchase order links them)
    db.add(models.PurchaseOrder(restaurant_id=1, supplier_id=1, inventory_item_id=1,
                                quantity_ordered=10, unit="kg", status="DELIVERED"))
    # give the burger real 30-day revenue so revenue-at-risk is non-zero
    for d in range(10):
        o = models.Order(restaurant_id=1, status=models.OrderStatus.SERVED,
                         payment_method=models.PaymentMethod.CASH, is_paid=True,
                         total=1000, created_at=utcnow() - timedelta(days=d))
        db.add(o)
        db.flush()
        db.add(models.OrderItem(order_id=o.id, menu_item_id=1, quantity=1, unit_price=1000))
    db.commit()
    return db


def test_graph_has_expected_nodes_and_edges(wired):
    g = build_graph(wired, 1)
    assert node_key("supplier", 1) in g.nodes
    assert node_key("ingredient", 1) in g.nodes
    assert node_key("menu_item", 1) in g.nodes
    assert node_key("category", "mains") in g.nodes
    # supplier supplies the ingredient; ingredient used in both dishes
    relations = {(e["source"], e["relation"], e["target"])
                 for edges in g.out.values() for e in edges}
    assert (node_key("supplier", 1), "supplies", node_key("ingredient", 1)) in relations
    assert (node_key("ingredient", 1), "used_in", node_key("menu_item", 1)) in relations


def test_supplier_impact_reaches_dishes_and_categories(wired):
    g = build_graph(wired, 1)
    affected, _edges = downstream(g, node_key("supplier", 1))
    assert node_key("ingredient", 1) in affected
    assert node_key("menu_item", 1) in affected
    assert node_key("menu_item", 2) in affected     # reachable (non-critical still an edge)
    assert node_key("category", "mains") in affected


def test_revenue_at_risk_counts_only_critical_dishes(wired):
    report = get_impact(wired, 1, "supplier", 1)
    assert report["available"] is True
    s = report["summary"]
    assert s["affected_dishes"] == 2          # both dishes are reachable
    assert s["critical_dishes"] == 1          # only the burger critically depends on chicken
    # revenue at risk is the burger's 30-day revenue (KES 100 * 10 orders = 100_000c), not the garnish dish
    assert s["revenue_at_risk_30d_cents"] > 0
    assert report["root"]["label"] == "Supplier A"


def test_dish_upstream_dependencies(wired):
    g = build_graph(wired, 1)
    deps, _ = upstream(g, node_key("menu_item", 1))
    assert node_key("ingredient", 1) in deps
    assert node_key("supplier", 1) in deps


def test_unknown_entity_degrades(wired):
    report = get_impact(wired, 1, "supplier", 999)
    assert report["available"] is False
