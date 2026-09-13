"""Owner feeds must not confuse restaurant keys with tenant keys."""
from datetime import timedelta

import pytest

import auth
import models
from time_utils import utcnow


@pytest.fixture
def scoped_owner(db_session):
    db = db_session
    db.add_all([models.Tenant(id=101, name="Owner tenant"),
                models.Tenant(id=202, name="Other tenant")])
    db.flush()
    db.add_all([
        models.Restaurant(id=202, tenant_id=101, name="Selected restaurant"),
        models.Restaurant(id=203, tenant_id=101, name="Sibling restaurant"),
        models.Restaurant(id=303, tenant_id=202, name="Foreign restaurant"),
    ])
    db.flush()
    user = models.User(tenant_id=101, active_restaurant_id=202,
                       email="scope-owner@example.com", hashed_password="unused",
                       role=models.Role.ADMIN)
    db.add(user)
    now = utcnow()
    day = (now + timedelta(hours=3)).date()
    for rid, name, cost in [(202, "Selected stock", 1000),
                            (203, "Sibling stock", 9000),
                            (303, "Foreign stock", 50000)]:
        db.add(models.InventoryItem(restaurant_id=rid, item_name=name,
                                    quantity=1, unit="kg", low_stock_threshold=5))
        staff = models.StaffMember(restaurant_id=rid, name=name)
        supplier = models.Supplier(restaurant_id=rid, name=name)
        db.add_all([staff, supplier])
        db.flush()
        db.add(models.LaborShift(restaurant_id=rid, staff_member_id=staff.id,
                                 shift_date=day, labor_cost=cost,
                                 actual_start=now - timedelta(hours=1)))
        db.add(models.PurchaseOrder(restaurant_id=rid, supplier_id=supplier.id,
                                    quantity_ordered=1, status="PENDING"))
    db.commit()
    token = auth.create_access_token({"sub": user.email})
    return user, {"Authorization": f"Bearer {token}"}


def test_overview_cards_are_scoped_to_selected_restaurant(client, db_session, scoped_owner):
    _, headers = scoped_owner
    response = client.get("/api/v1/overview/today", headers=headers)
    assert response.status_code == 200, response.text
    feed = response.json()
    assert feed["restaurant_name"] == "Selected restaurant"
    assert [item["name"] for item in feed["stock"]["low_stock"]] == ["Selected stock"]
    assert feed["staff"]["scheduled"] == 1
    assert feed["staff"]["on_shift"] == 1
    titles = [card["title"] for card in feed["attention"]]
    assert any("Selected stock" in title for title in titles)
    assert "1 purchase order(s) awaiting approval" in titles
    assert not any("Sibling" in title or "Foreign" in title for title in titles)


def test_attention_decision_uses_tenant_key_not_restaurant_key(client, db_session, scoped_owner):
    user, headers = scoped_owner
    stock = db_session.query(models.InventoryItem).filter_by(restaurant_id=202).one()
    key = f"stock-{stock.id}"
    response = client.post(f"/api/v1/overview/attention/{key}/decision",
                           json={"decision": "approved"}, headers=headers)
    assert response.status_code == 200, response.text
    feed = client.get("/api/v1/overview/today", headers=headers).json()
    assert key not in [card["id"] for card in feed["attention"]]
    decision = db_session.query(models.AttentionDecision).filter_by(card_key=key).one()
    assert decision.tenant_id == user.tenant_id == 101
    db_session.refresh(stock)
    assert stock.quantity == 1  # Recording advice never changes operational stock.


@pytest.mark.parametrize("path", ["/api/v1/overview/today", "/api/v1/reports/daily?narrate=false"])
def test_foreign_active_restaurant_fails_closed(client, db_session, scoped_owner, path):
    user, headers = scoped_owner
    user.active_restaurant_id = 303
    db_session.commit()
    response = client.get(path, headers=headers)
    assert response.status_code == 404, response.text


def test_missing_selection_resolves_inside_owner_tenant(client, db_session, scoped_owner):
    user, headers = scoped_owner
    user.active_restaurant_id = None
    db_session.commit()
    response = client.get("/api/v1/overview/today", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["restaurant_name"] == "Selected restaurant"
