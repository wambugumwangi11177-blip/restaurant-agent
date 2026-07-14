"""
End-to-end verification of the whole agentic system (all phases composed).

One seeded restaurant, driven through the real FastAPI app over HTTP, exercising
every new surface in sequence so we prove they INTEROPERATE, not just that each
works in isolation:

  Phase 1  GET  /ai/decisions          ranked cross-agent decisions
  Phase 2  POST /ai/simulate           what-if projection
  Phase 6  GET  /ai/graph/impact       knowledge-graph blast radius
  Phase 3  POST /ai/strategy           CEO agent (deterministic fallback, no LLM)
  Phase 9  POST /ai/strategy/plan      autonomous week-by-week plan
  Phase 9  GET  /ai/feedback           self-evaluation loop
  Phase 4  GET  /ai/forecast/twin      digital twin
  Phase 5  GET  /ai/usage              cost in money + scorecards
  Phase 8  POST /ai/workflows/...      durable workflow start → approve → complete
  Phase 11 GET  /ai/plugins            marketplace registry
  Phase 10 GET  /enterprise/benchmark  cross-location benchmark
"""

from datetime import time, timedelta

import auth
import models
from time_utils import utcnow


def _admin(db):
    tenant = models.Tenant(name="E2E Co")
    db.add(tenant)
    db.commit()
    user = models.User(tenant_id=tenant.id, email="e2e@example.com",
                       hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN)
    restaurant = models.Restaurant(tenant_id=tenant.id, name="E2E Grill", address="Nairobi")
    db.add_all([user, restaurant])
    db.commit()
    token = auth.create_access_token({"sub": user.email})
    return tenant, restaurant, {"Authorization": f"Bearer {token}"}


def _seed(db, restaurant_id):
    """A below-margin item with history (→ pricing decision), a low-stock item +
    supplier (→ inventory decision + reorder workflow), and a drink."""
    items = [
        models.MenuItem(id=1001, restaurant_id=restaurant_id, name="ThinBurger",
                        price=1000, cost_price=900, category="main"),
        models.MenuItem(id=1002, restaurant_id=restaurant_id, name="Cola",
                        price=300, cost_price=60, category="drinks"),
    ]
    inv = models.InventoryItem(id=2001, restaurant_id=restaurant_id, item_name="Beef",
                               quantity=1.0, unit="kg", low_stock_threshold=10)
    sup = models.Supplier(id=3001, restaurant_id=restaurant_id, name="Supplier A", is_active=True)
    db.add_all(items + [inv, sup])
    db.commit()
    db.add(models.MenuIngredient(menu_item_id=1001, inventory_item_id=2001,
                                 quantity_per_serving=0.2, is_critical=True))
    db.add(models.PurchaseOrder(restaurant_id=restaurant_id, supplier_id=3001,
                                inventory_item_id=2001, quantity_ordered=10, status="DELIVERED"))
    db.commit()
    now = utcnow()
    for d in range(30):
        o = models.Order(restaurant_id=restaurant_id, status=models.OrderStatus.SERVED,
                         payment_method=models.PaymentMethod.CASH, is_paid=True,
                         total=1300, created_at=now - timedelta(days=d))
        db.add(o)
        db.flush()
        db.add(models.OrderItem(order_id=o.id, menu_item_id=1001, quantity=1, unit_price=1000))
        db.add(models.OrderItem(order_id=o.id, menu_item_id=1002, quantity=1, unit_price=300))
    db.commit()


def test_full_agentic_pipeline(client, db_session):
    _tenant, restaurant, H = _admin(db_session)
    _seed(db_session, restaurant.id)

    # ── Phase 1: ranked decisions across agents ──────────────────────────────
    r = client.get("/ai/decisions", headers=H)
    assert r.status_code == 200
    decisions = r.json()
    assert decisions["summary"]["total_decisions"] >= 1
    cats = {d["category"] for d in decisions["decisions"]}
    assert "pricing" in cats                       # below-floor item surfaced
    top = decisions["decisions"][0]
    assert 0 <= top["priority_score"] <= 100

    # ── Phase 2: simulate a price change on the pricing item ─────────────────
    r = client.post("/ai/simulate", headers=H,
                    json={"change": {"type": "price_change", "item_id": 1001, "new_price": 1200}})
    assert r.status_code == 200
    sim = r.json()
    assert sim["available"] and sim["verdict"] in ("YES", "CAUTION", "NO")

    # ── Phase 6: knowledge-graph impact of the supplier ──────────────────────
    r = client.get("/ai/graph/impact?entity=supplier&id=3001", headers=H)
    assert r.status_code == 200
    graph = r.json()
    assert graph["available"] and graph["summary"]["affected_dishes"] >= 1

    # ── Phase 3: CEO strategy (deterministic fallback — no LLM key in tests) ──
    r = client.post("/ai/strategy", headers=H, json={"goal": "increase monthly profit by KES 50,000"})
    assert r.status_code == 200
    strat = r.json()
    assert strat["available"] and strat["mode"] == "deterministic"
    assert strat["strategy"]["steps"]

    # ── Phase 9: autonomous plan + feedback loop ─────────────────────────────
    r = client.post("/ai/strategy/plan", headers=H, json={"goal": "grow profit", "horizon_weeks": 3})
    assert r.status_code == 200 and r.json()["available"]
    assert len(r.json()["weeks"]) >= 1
    r = client.get("/ai/feedback", headers=H)
    assert r.status_code == 200 and "agent_reliability" in r.json()

    # ── Phase 4: digital twin projection ─────────────────────────────────────
    r = client.get("/ai/forecast/twin?horizon=30", headers=H)
    assert r.status_code == 200
    twin = r.json()
    assert twin["available"] and twin["summary"]["projected_revenue_cents"] > 0

    # ── Phase 5: AI-Ops cost (money) + scorecards ────────────────────────────
    r = client.get("/ai/usage", headers=H)
    assert r.status_code == 200
    usage = r.json()
    assert "cost_usd" in usage["llm"] and "economics" in usage and "scorecards" in usage

    # ── Phase 8: durable workflow — start → approve → deliver → complete ──────
    r = client.post("/ai/workflows/low_stock_reorder/start", headers=H)
    assert r.status_code == 200
    wf = r.json()
    assert wf["available"] and wf["status"] == "awaiting"    # paused on approval
    run_id = wf["id"]
    r = client.post(f"/ai/workflows/{run_id}/resume", headers=H, json={"decision": "approve"})
    assert r.json()["status"] == "awaiting"                  # now awaiting delivery
    r = client.post(f"/ai/workflows/{run_id}/resume", headers=H, json={"decision": "approve"})
    assert r.json()["status"] == "completed"
    # a real PO was created only after approval
    assert db_session.query(models.PurchaseOrder).filter_by(restaurant_id=restaurant.id).count() == 2

    # ── Phase 11: marketplace registry reachable ─────────────────────────────
    r = client.get("/ai/plugins", headers=H)
    assert r.status_code == 200 and "plugins" in r.json()

    # ── Phase 10: enterprise benchmark over an org with this site ────────────
    org = models.Organization(tenant_id=_tenant.id, name="E2E Chain")
    db_session.add(org)
    db_session.commit()
    restaurant.organization_id = org.id
    db_session.commit()
    r = client.get(f"/enterprise/benchmark?organization_id={org.id}", headers=H)
    assert r.status_code == 200
    bench = r.json()
    assert bench["available"] and bench["site_count"] == 1
    assert bench["sites"][0]["revenue_30d_cents"] > 0
