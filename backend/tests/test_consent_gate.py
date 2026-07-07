"""
Minimal consent gate for customer-facing PII collection (models.CustomerConsent).
An order with contact details requires explicit consent; an anonymous order
(no phone) doesn't need it, since there's no PII to consent to.
"""

import models


def _seed_menu(db_session):
    r = models.Restaurant(id=1, tenant_id=None, name="Test Bistro", address="x")
    item = models.MenuItem(id=1, restaurant_id=1, name="Burger", price=50000, is_available=True)
    db_session.add_all([r, item])
    db_session.commit()


def test_order_with_phone_and_no_consent_is_rejected(client, db_session):
    _seed_menu(db_session)
    resp = client.post("/orders/public?restaurant_id=1", json={
        "items": [{"menu_item_id": 1, "quantity": 1}],
        "payment_method": "cash",
        "customer_name": "Jane",
        "customer_phone": "0712345678",
        "consent": False,
    })
    assert resp.status_code == 400

    consents = db_session.query(models.CustomerConsent).all()
    assert consents == []


def test_order_with_phone_and_consent_is_recorded(client, db_session):
    _seed_menu(db_session)
    resp = client.post("/orders/public?restaurant_id=1", json={
        "items": [{"menu_item_id": 1, "quantity": 1}],
        "payment_method": "cash",
        "customer_name": "Jane",
        "customer_phone": "0712345678",
        "consent": True,
    })
    assert resp.status_code == 200

    consent = db_session.query(models.CustomerConsent).filter(
        models.CustomerConsent.customer_phone == "0712345678"
    ).first()
    assert consent is not None
    assert consent.restaurant_id == 1
    assert consent.purpose == "order_checkout"


def test_anonymous_order_without_phone_does_not_require_consent(client, db_session):
    _seed_menu(db_session)
    resp = client.post("/orders/public?restaurant_id=1", json={
        "items": [{"menu_item_id": 1, "quantity": 1}],
        "payment_method": "cash",
        "consent": False,
    })
    assert resp.status_code == 200

    consents = db_session.query(models.CustomerConsent).all()
    assert consents == []
