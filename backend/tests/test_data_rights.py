"""
Data-subject rights endpoints (KDPA / DPA / Privacy Policy):
  • Portability — CSV export, tenant-scoped.
  • Erasure    — scrub customer PII from orders + reservations, delete consent,
                 add opt-out. Tenant-scoped.
"""

from datetime import date, time
import models
import auth


def _tenant(db_session, suffix: str):
    tenant = models.Tenant(name=f"Tenant {suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id, email=f"owner_{suffix}@example.com",
        hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN,
    )
    db_session.add(user)
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()
    return restaurant, {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email})}"}


def test_orders_csv_export_is_tenant_scoped(client, db_session):
    r_a, hdr_a = _tenant(db_session, "a")
    r_b, hdr_b = _tenant(db_session, "b")
    db_session.add(models.Order(
        restaurant_id=r_a.id, status=models.OrderStatus.SERVED,
        payment_method=models.PaymentMethod.CASH, is_paid=True, total=12300,
        customer_name="Alice", customer_phone="0712345678",
    ))
    db_session.add(models.Order(
        restaurant_id=r_b.id, status=models.OrderStatus.SERVED,
        payment_method=models.PaymentMethod.MPESA, is_paid=True, total=99900,
        customer_name="Bob", customer_phone="0722222222",
    ))
    db_session.commit()

    resp = client.get("/data/export/orders.csv", headers=hdr_a)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    body = resp.text
    assert "Alice" in body and "123.0" in body   # own data, KES
    assert "Bob" not in body and "0722222222" not in body  # other tenant excluded


def test_erase_customer_scrubs_pii_and_records_optout(client, db_session):
    r_a, hdr_a = _tenant(db_session, "a")
    order = models.Order(
        restaurant_id=r_a.id, status=models.OrderStatus.SERVED,
        payment_method=models.PaymentMethod.CASH, is_paid=True, total=5000,
        customer_name="Alice", customer_phone="0712345678",
    )
    resv = models.Reservation(
        restaurant_id=r_a.id, customer_name="Alice", customer_phone="+254712345678",
        customer_email="a@x.com", party_size=2,
        reservation_date=date(2026, 7, 10), reservation_time=time(19, 0),
        status=models.ReservationStatus.CONFIRMED,
    )
    consent = models.CustomerConsent(
        restaurant_id=r_a.id, customer_phone="0712345678", purpose="order_checkout",
    )
    db_session.add_all([order, resv, consent])
    db_session.commit()
    order_id, resv_id = order.id, resv.id

    resp = client.post("/data/erase-customer",
                       json={"customer_phone": "0712345678"}, headers=hdr_a)
    assert resp.status_code == 200
    data = resp.json()
    assert data["orders_scrubbed"] == 1
    assert data["reservations_scrubbed"] == 1
    assert data["consents_deleted"] == 1

    db_session.expire_all()
    o = db_session.query(models.Order).filter(models.Order.id == order_id).first()
    assert o is not None                 # record kept (financial integrity)
    assert o.customer_name is None       # ...but PII scrubbed
    assert o.customer_phone is None
    rv = db_session.query(models.Reservation).filter(models.Reservation.id == resv_id).first()
    assert rv.customer_phone is None and rv.customer_email is None
    assert db_session.query(models.CustomerConsent).count() == 0
    # Future marketing is now suppressed for this number.
    from ai.whatsapp.optout import is_opted_out
    assert is_opted_out(db_session, "0712345678") is True


def test_erase_customer_does_not_touch_other_tenant(client, db_session):
    r_a, hdr_a = _tenant(db_session, "a")
    r_b, hdr_b = _tenant(db_session, "b")
    order_b = models.Order(
        restaurant_id=r_b.id, status=models.OrderStatus.SERVED,
        payment_method=models.PaymentMethod.CASH, is_paid=True, total=5000,
        customer_name="Bob", customer_phone="0712345678",  # same number, other tenant
    )
    db_session.add(order_b)
    db_session.commit()
    order_b_id = order_b.id

    resp = client.post("/data/erase-customer",
                       json={"customer_phone": "0712345678"}, headers=hdr_a)
    assert resp.status_code == 200
    assert resp.json()["orders_scrubbed"] == 0  # nothing of tenant A's matched

    db_session.expire_all()
    ob = db_session.query(models.Order).filter(models.Order.id == order_b_id).first()
    assert ob.customer_name == "Bob"  # tenant B untouched


def test_erase_customer_cannot_optout_a_foreign_tenants_number(client, db_session):
    """
    `CustomerOptOut` is phone-global (no restaurant_id) — a suppressed number is
    suppressed for every tenant. So tenant A submitting a number that belongs
    only to tenant B must NOT create an opt-out, or A could permanently kill B's
    ability to message its own customer.
    """
    r_a, hdr_a = _tenant(db_session, "a")
    r_b, _ = _tenant(db_session, "b")
    db_session.add(models.Order(
        restaurant_id=r_b.id, status=models.OrderStatus.SERVED,
        payment_method=models.PaymentMethod.CASH, is_paid=True, total=5000,
        customer_name="Bob", customer_phone="0722222222",  # only tenant B knows it
    ))
    db_session.commit()

    resp = client.post("/data/erase-customer",
                       json={"customer_phone": "0722222222"}, headers=hdr_a)
    assert resp.status_code == 200
    assert resp.json()["status"] == "no_data"

    from ai.whatsapp.optout import is_opted_out
    db_session.expire_all()
    assert is_opted_out(db_session, "0722222222") is False  # B can still reach Bob


def test_erase_customer_optout_still_works_for_own_number(client, db_session):
    """The guard must not break the legitimate path: a phone the caller's own
    tenant holds data for still gets globally suppressed."""
    r_a, hdr_a = _tenant(db_session, "a")
    db_session.add(models.Order(
        restaurant_id=r_a.id, status=models.OrderStatus.SERVED,
        payment_method=models.PaymentMethod.CASH, is_paid=True, total=5000,
        customer_name="Alice", customer_phone="0712345678",
    ))
    db_session.commit()

    resp = client.post("/data/erase-customer",
                       json={"customer_phone": "0712345678"}, headers=hdr_a)
    assert resp.json()["orders_scrubbed"] == 1

    from ai.whatsapp.optout import is_opted_out
    db_session.expire_all()
    assert is_opted_out(db_session, "0712345678") is True
