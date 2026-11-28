import json

from tests.test_store_intake import JPEG, _day_photos, _unlock
from tests.test_storekeeper_foundation import _add_staff, _auth, _tenant, _token


def test_multiline_delivery_by_item_id(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-ml@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-ml@eleven.leviii", __import__("models").StaffRole.STOCKKEEPER)
    _unlock(client, jack)
    sup = client.post(
        "/api/v1/store/suppliers",
        headers=_auth(_token(jack)),
        json={"name": "Farm", "phone": "", "brings": "main food"},
    ).json()
    client.post(
        "/api/v1/store/items/opening",
        headers=_auth(_token(jack)),
        json={"item_name": "Rice", "quantity": 5, "unit": "kg", "zone": "Main store"},
    )
    client.post(
        "/api/v1/store/items/opening",
        headers=_auth(_token(owner)),
        json={"item_name": "Oil", "quantity": 2, "unit": "L", "zone": "Main store"},
    )
    _day_photos(client, jack, "open")
    items = client.get("/api/v1/store/items", headers=_auth(_token(jack))).json()["items"]
    rice = next(i for i in items if i["item_name"] == "Rice")
    oil = next(i for i in items if i["item_name"] == "Oil")
    lines = json.dumps(
        [
            {"item_id": rice["id"], "quantity": 3},
            {"item_id": oil["id"], "quantity": 1},
        ]
    )
    saved = client.post(
        "/api/v1/store/deliveries",
        headers=_auth(_token(jack)),
        data={"supplier_id": str(sup["id"]), "lines": lines},
        files=[
            ("invoice", ("invoice.jpg", JPEG, "image/jpeg")),
            ("goods", ("goods.jpg", JPEG, "image/jpeg")),
        ],
    )
    assert saved.status_code == 201, saved.text
    listed = client.get("/api/v1/store/deliveries", headers=_auth(_token(jack))).json()
    assert len(listed[0]["lines"]) == 2
    after = client.get("/api/v1/store/items", headers=_auth(_token(jack))).json()["items"]
    rice_after = next(i for i in after if i["id"] == rice["id"])
    assert rice_after["quantity"] == 8

def test_delivery_adds_to_stock_that_has_no_zone_rows(client, db_session):
    import models

    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-legacy@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-legacy@eleven.leviii", models.StaffRole.STOCKKEEPER)
    _unlock(client, jack)
    sup = client.post(
        "/api/v1/store/suppliers",
        headers=_auth(_token(jack)),
        json={"name": "Farm", "phone": "", "brings": "main food"},
    ).json()
    cabbage = models.InventoryItem(restaurant_id=restaurant.id, item_name="Cabbage", quantity=7, unit="kg", cost_per_unit=0)
    db_session.add(cabbage)
    db_session.commit()
    _day_photos(client, jack, "open")
    saved = client.post(
        "/api/v1/store/deliveries",
        headers=_auth(_token(jack)),
        data={"supplier_id": str(sup["id"]), "lines": json.dumps([{"item_id": cabbage.id, "quantity": 2.5}])},
        files=[
            ("invoice", ("invoice.jpg", JPEG, "image/jpeg")),
            ("goods", ("goods.jpg", JPEG, "image/jpeg")),
        ],
    )
    assert saved.status_code == 201, saved.text
    db_session.refresh(cabbage)
    assert cabbage.quantity == 9.5
    balances = db_session.query(models.StockBalance).filter_by(inventory_item_id=cabbage.id).all()
    assert [b.quantity for b in balances] == [9.5]
