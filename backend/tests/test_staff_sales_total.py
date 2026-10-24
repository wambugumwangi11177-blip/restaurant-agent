"""Staff sales must not sum the 200-row order page."""
import auth
import models
from routers.deps import get_or_create_restaurant
from time_utils import utcnow


def _user(db, suffix, role, staff_role):
    tenant = models.Tenant(name=f"Sales{suffix}")
    db.add(tenant)
    db.commit()
    user = models.User(
        tenant_id=tenant.id, email=f"{suffix}@sales.test", hashed_password=auth.get_password_hash("x"),
        role=role, staff_role=staff_role, token_version=0,
    )
    db.add(user)
    db.commit()
    restaurant = get_or_create_restaurant(db, user)
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return token, restaurant


def test_trading_day_total_includes_orders_past_the_page_cap(client, db_session):
    token, restaurant = _user(db_session, "mgr", models.Role.STAFF, models.StaffRole.MANAGER)
    now = utcnow()
    db_session.add(models.Order(
        restaurant_id=restaurant.id, status=models.OrderStatus.SERVED, is_paid=True,
        payment_method=models.PaymentMethod.CASH, total=50_000, created_at=now.replace(year=now.year - 1),
    ))
    db_session.add_all([
        models.Order(
            restaurant_id=restaurant.id, status=models.OrderStatus.SERVED, is_paid=True,
            payment_method=models.PaymentMethod.CASH, total=100, created_at=now,
        )
        for _ in range(201)
    ])
    db_session.commit()
    headers = {"Authorization": f"Bearer {token}"}
    page = client.get("/api/v1/orders/", headers=headers)
    assert page.status_code == 200
    assert len(page.json()) == 200
    total = client.get("/api/v1/sales/today", headers=headers)
    assert total.status_code == 200, total.text
    body = total.json()
    assert body["orders"] == 201
    assert body["revenue_kes"] == 201.0
    assert "service" in body["window_label"]
    assert client.get("/api/v1/overview/today", headers=headers).status_code == 403


def test_accountant_can_read_the_total_and_a_waiter_cannot(client, db_session):
    accountant, restaurant = _user(db_session, "acct", models.Role.STAFF, models.StaffRole.CONTROLLER)
    waiter, _ = _user(db_session, "wait", models.Role.STAFF, models.StaffRole.WAITER)
    db_session.add(models.Order(
        restaurant_id=restaurant.id, status=models.OrderStatus.SERVED, is_paid=True,
        payment_method=models.PaymentMethod.MPESA, total=25000, created_at=utcnow(),
    ))
    db_session.commit()
    ok = client.get("/api/v1/sales/today", headers={"Authorization": f"Bearer {accountant}"})
    assert ok.status_code == 200
    assert ok.json()["orders"] == 1
    assert ok.json()["revenue_kes"] == 250.0
    denied = client.get("/api/v1/sales/today", headers={"Authorization": f"Bearer {waiter}"})
    assert denied.status_code == 403


def test_another_restaurants_manager_does_not_see_the_total(client, db_session):
    _token_a, restaurant_a = _user(db_session, "a", models.Role.STAFF, models.StaffRole.MANAGER)
    token_b, _restaurant_b = _user(db_session, "b", models.Role.STAFF, models.StaffRole.MANAGER)
    db_session.add_all([
        models.Order(
            restaurant_id=restaurant_a.id, status=models.OrderStatus.SERVED, is_paid=True,
            payment_method=models.PaymentMethod.CASH, total=100, created_at=utcnow(),
        )
        for _ in range(3)
    ])
    db_session.commit()
    mine = client.get("/api/v1/sales/today", headers={"Authorization": f"Bearer {_token_a}"})
    theirs = client.get("/api/v1/sales/today", headers={"Authorization": f"Bearer {token_b}"})
    assert mine.status_code == 200 and mine.json()["orders"] == 3
    assert theirs.status_code == 200 and theirs.json()["orders"] == 0
    assert theirs.json()["revenue_kes"] == 0
