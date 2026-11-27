"""Restock invoice draft + routing + Jack price hiding."""
import models
from money_visibility import money_keys_in
from services.restock_workflow import build_invoice_draft, placement_actor_role
from tests.test_storekeeper_foundation import _auth, _tenant, _token


def test_placement_actor_follows_routing_mode(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "owner-route@eleven.leviii")
    restaurant.restock_routing_mode = "staples_self"
    assert placement_actor_role(restaurant) == "stockkeeper"
    restaurant.restock_routing_mode = "flag_office"
    assert placement_actor_role(restaurant) == "controller"
    restaurant.restock_routing_mode = "owner_approves"
    assert placement_actor_role(restaurant) == "owner"


def test_jack_restock_list_hides_prices(client, db_session):
    from tests.test_storekeeper_foundation import _add_staff

    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-jack-restock@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-restock@eleven.leviii", models.StaffRole.STOCKKEEPER)
    supplier = models.Supplier(restaurant_id=restaurant.id, name="Fresh")
    item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Rice", quantity=2, unit="kg", cost_per_unit=120.0)
    db_session.add(supplier)
    db_session.add(item)
    db_session.flush()
    po = models.PurchaseOrder(
        restaurant_id=restaurant.id,
        supplier_id=supplier.id,
        inventory_item_id=item.id,
        quantity_ordered=5,
        unit="kg",
        cost_per_unit=12000,
        total_cost=60000,
        status="APPROVED",
    )
    db_session.add(po)
    db_session.commit()
    jack_resp = client.get("/api/v1/store/restock", headers=_auth(_token(jack)))
    assert jack_resp.status_code == 200
    payload = jack_resp.json()["orders"][0]
    assert not money_keys_in(payload)
    owner_resp = client.get("/api/v1/store/restock", headers=_auth(_token(owner)))
    assert owner_resp.json()["orders"][0].get("total_cost") == 60000


def test_invoice_draft_suggest_only(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "owner-draft@eleven.leviii")
    supplier = models.Supplier(restaurant_id=restaurant.id, name="Fresh")
    item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Oil", quantity=1, unit="L", cost_per_unit=500.0)
    db_session.add_all([supplier, item])
    db_session.flush()
    po = models.PurchaseOrder(
        restaurant_id=restaurant.id,
        supplier_id=supplier.id,
        inventory_item_id=item.id,
        quantity_ordered=3,
        unit="L",
        cost_per_unit=50000,
        total_cost=150000,
        status="PENDING",
    )
    draft = build_invoice_draft(db_session, po)
    assert draft["lines"][0]["unit_price_cents"] == 50000
    assert "not changed" in draft["note"].lower()