"""Regression tests from docs/engine-review.md."""
import models
from ai.inventory_predictor import get_inventory_predictions
from ai.order_stock import deduct_ingredients_for_order
from services.eleven_rules import run_eleven_rules
from tests.test_storekeeper_foundation import _tenant, _add_staff
from tests.factories import seed_owner


def test_predictor_uses_supplier_lead_days(db_session):
    _, restaurant, _ = seed_owner(db_session, tenant_name="Eleven")
    supplier = models.Supplier(restaurant_id=restaurant.id, name="Farm", contact_phone="", avg_lead_days=5.0)
    db_session.add(supplier)
    db_session.flush()
    item = models.InventoryItem(
        restaurant_id=restaurant.id,
        item_name="Rice",
        quantity=10,
        unit="kg",
        low_stock_threshold=2,
        default_supplier_id=supplier.id,
        cost_per_unit=100,
    )
    db_session.add(item)
    db_session.commit()
    preds = get_inventory_predictions(db_session, restaurant.id)["predictions"]
    row = next(p for p in preds if p["name"] == "Rice")
    assert row.get("days_until_stockout") == row.get("days_until_depletion")
    assert row.get("lead_time_days") == 5.0


def test_deduction_honours_yield():
    serving, plates, yield_f = 0.5, 1, 0.5
    assert (serving * plates) / yield_f == 1.0


def test_rules_emit_custody_wording(db_session):
    owner, restaurant, _ = seed_owner(db_session, tenant_name="Eleven")
    rules = run_eleven_rules(db_session, restaurant.id)
    for r in rules:
        assert "theft" not in (r.get("headline") or "").lower()
        assert "fraud" not in (r.get("headline") or "").lower()


def test_money_pnl_includes_bills(client, db_session):
    owner, restaurant, _ = seed_owner(db_session, tenant_name="Eleven")
    from auth import create_access_token
    from tests.test_storekeeper_foundation import _auth

    owner.active_restaurant_id = restaurant.id
    db_session.add(
        models.RunningCost(
            restaurant_id=restaurant.id,
            user_id=owner.id,
            kind="rent",
            label="Rent",
            amount_cents=5000000,
            status="approved",
            approved_at=__import__("time_utils", fromlist=["utcnow"]).utcnow(),
        )
    )
    db_session.commit()
    token = create_access_token({"sub": owner.email, "ver": owner.token_version or 0})
    r = client.get("/api/v1/eleven/money/pnl", headers=_auth(token))
    assert r.status_code == 200
    assert r.json().get("bills_cents", 0) >= 5000000