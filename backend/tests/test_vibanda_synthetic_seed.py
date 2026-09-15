"""The staging seed must be executable only against the isolated test DB."""
from __future__ import annotations

from datetime import timedelta

from models import Order, Restaurant, Tenant


def test_synthetic_seed_creates_only_a_two_month_vibanda_tenant(db_session, monkeypatch):
    """Exercise the real seed path, never merely its command text.

    ``db_session`` is backed by the test suite's throwaway SQLite file. The
    production DB guard in conftest rejects any remote DATABASE_URL before this
    test can run.
    """
    monkeypatch.setenv("SYNTHETIC_DATA_ALLOWED", "true")
    monkeypatch.setattr(
        "sys.argv",
        [
            "seed_vibanda_synthetic.py",
            "--yes-synthetic-data",
            "--owner-email",
            "synthetic-owner@example.test",
            "--owner-password",
            "not-a-production-password",
        ],
    )

    from scripts import seed_vibanda_synthetic

    assert seed_vibanda_synthetic.main() == 0

    synthetic = db_session.query(Tenant).filter_by(name=seed_vibanda_synthetic.SYNTHETIC_TENANT).one()
    restaurant = db_session.query(Restaurant).filter_by(tenant_id=synthetic.id).one()
    orders = db_session.query(Order).filter_by(restaurant_id=restaurant.id).all()

    assert restaurant.name == "Vibanda Village — Synthetic"
    assert not db_session.query(Tenant).filter_by(name="Vibanda Village").count()
    assert orders
    oldest = min(order.created_at for order in orders)
    newest = max(order.created_at for order in orders)
    assert newest - oldest >= timedelta(days=59)
