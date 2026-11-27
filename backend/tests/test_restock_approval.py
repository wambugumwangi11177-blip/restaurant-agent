"""Restock PO owner approval."""
import models
from tests.test_storekeeper_foundation import _auth, _tenant, _token


def test_owner_can_decline_pending_restock(client, db_session):
    _, owner, restaurant = _tenant(db_session, "Eleven", "owner-restock@eleven.leviii")
    supplier = models.Supplier(restaurant_id=restaurant.id, name="Fresh")
    item = models.InventoryItem(restaurant_id=restaurant.id, item_name="Rice", quantity=1, unit="kg")
    db_session.add(supplier)
    db_session.add(item)
    db_session.flush()
    po = models.PurchaseOrder(
        restaurant_id=restaurant.id,
        supplier_id=supplier.id,
        inventory_item_id=item.id,
        quantity_ordered=10,
        unit="kg",
        status="PENDING",
    )
    db_session.add(po)
    db_session.commit()
    response = client.post(
        "/api/v1/store/approvals",
        headers=_auth(_token(owner)),
        json={"kind": "restock", "id": po.id, "decision": "decline"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "DECLINED"