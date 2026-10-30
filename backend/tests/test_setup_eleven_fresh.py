"""Fresh Eleven setup must stay idempotent and create no orders."""
from models import Order, Restaurant, Tenant, User
from scripts.setup_eleven_fresh import ensure_eleven_fresh


def test_setup_eleven_fresh_is_idempotent(db_session, monkeypatch):
    monkeypatch.setenv("ELEVEN_SETUP_ALLOWED", "true")
    email = "eleven-owner@example.test"
    pwd = "Eleven-Test-Pass-99!"

    r1 = ensure_eleven_fresh(
        db_session,
        owner_email=email,
        owner_password=pwd,
        tenant_name="Eleven",
        restaurant_name="Eleven",
    )
    r2 = ensure_eleven_fresh(
        db_session,
        owner_email=email,
        owner_password=pwd,
        tenant_name="Eleven",
        restaurant_name="Eleven",
    )
    assert r1.id == r2.id
    assert db_session.query(Tenant).filter_by(name="Eleven").count() == 1
    assert db_session.query(User).filter_by(email=email).count() == 1
    assert db_session.query(Order).filter_by(restaurant_id=r1.id).count() == 0
