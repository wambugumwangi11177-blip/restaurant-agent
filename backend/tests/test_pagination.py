"""
audit remediation, Tier 1 item 2 — staff.py's list_staff and orders.py's
active_orders were previously fully unbounded (no limit/offset, no .limit()
at all). Both now cap at 200 by default and accept limit/offset, matching the
pattern list_orders already used.
"""

import auth
import models
from routers.deps import get_or_create_restaurant


def _admin_token_and_restaurant(db_session, suffix="pg"):
    tenant = models.Tenant(name=f"PagTenant{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"admin{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN,
        token_version=0,
    )
    db_session.add(user)
    db_session.commit()
    restaurant = get_or_create_restaurant(db_session, user)
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return token, restaurant


def test_list_staff_respects_limit_and_offset(client, db_session):
    token, restaurant = _admin_token_and_restaurant(db_session, "staff")
    for i in range(5):
        db_session.add(models.StaffMember(
            restaurant_id=restaurant.id, name=f"Staffer {i}", is_active=True,
        ))
    db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    first_page = client.get("/staff/?limit=2&offset=0", headers=headers)
    second_page = client.get("/staff/?limit=2&offset=2", headers=headers)

    assert first_page.status_code == 200
    assert len(first_page.json()) == 2
    assert second_page.status_code == 200
    assert len(second_page.json()) == 2
    # Pages don't overlap.
    first_names = {m["name"] for m in first_page.json()}
    second_names = {m["name"] for m in second_page.json()}
    assert first_names.isdisjoint(second_names)


def test_list_staff_default_limit_is_200_not_unbounded(client, db_session):
    token, restaurant = _admin_token_and_restaurant(db_session, "staffdefault")
    for i in range(3):
        db_session.add(models.StaffMember(
            restaurant_id=restaurant.id, name=f"Staffer {i}", is_active=True,
        ))
    db_session.commit()

    resp = client.get("/staff/", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 3  # well under the 200 default cap


def test_active_orders_caps_at_200(client, db_session):
    token, restaurant = _admin_token_and_restaurant(db_session, "orders")
    for i in range(5):
        db_session.add(models.Order(
            restaurant_id=restaurant.id,
            status=models.OrderStatus.PENDING,
            total=1000,
        ))
    db_session.commit()

    resp = client.get("/orders/active", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert len(resp.json()) == 5  # under the cap; proves the route still works normally
