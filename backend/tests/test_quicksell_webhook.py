"""QuickSell POS webhook for Eleven: auth, mirror dedupe, timezone, orders."""
from __future__ import annotations

import pytest

from models import Order, Restaurant, Role, StaffRole, Tenant, User
from auth import get_password_hash

_KEY = "test-quicksell-key"


@pytest.fixture(autouse=True)
def _quicksell_key(monkeypatch):
    monkeypatch.setenv("QUICKSELL_API_KEY", _KEY)


@pytest.fixture(autouse=True)
def _mirror_tables(db_env):
    import database
    from integration.models import Base as IntegrationBase

    IntegrationBase.metadata.create_all(bind=database.engine)


@pytest.fixture
def eleven_restaurant(db_session):
    tenant = Tenant(name="Eleven")
    db_session.add(tenant)
    db_session.flush()
    user = User(
        tenant_id=tenant.id,
        email="eleven-owner@example.test",
        hashed_password=get_password_hash("Eleven-Test-Pass-99!"),
        role=Role.ADMIN,
        staff_role=StaffRole.OWNER,
    )
    restaurant = Restaurant(tenant_id=tenant.id, name="Eleven", address="")
    db_session.add_all([user, restaurant])
    db_session.commit()
    return restaurant


def _post(client, body, key=_KEY):
    headers = {"x-api-key": key} if key is not None else {}
    return client.post("/webhooks/quicksell/data", json=body, headers=headers)


def _sale(source_id="QS-001", occurred_at="2026-09-19T14:30:00+03:00", total_cents=125050):
    return {
        "entity": "sale",
        "records": [{
            "source_id": source_id,
            "occurred_at": occurred_at,
            "total_cents": total_cents,
        }],
    }


def test_missing_key_rejected(client, eleven_restaurant):
    assert _post(client, _sale(), key=None).status_code == 401


def test_wrong_key_rejected(client, eleven_restaurant):
    assert _post(client, _sale(), key="bad").status_code == 401


def test_duplicate_idempotent(client, db_session, eleven_restaurant):
    assert _post(client, _sale()).status_code == 200
    second = _post(client, _sale())
    assert second.status_code == 200
    assert second.json()["duplicates_ignored"] == 1
    assert db_session.query(Order).filter(Order.restaurant_id == eleven_restaurant.id).count() == 1


def test_stores_order_with_nairobi_day(client, db_session, eleven_restaurant):
    res = _post(client, _sale(occurred_at="2026-09-19T23:30:00+03:00"))
    assert res.status_code == 200
    assert res.json()["nairobi_business_days"] == ["2026-09-19"]
    order = db_session.query(Order).one()
    assert order.total == 125050
    assert order.notes == "quicksell:QS-001"


def test_late_night_utc_maps_to_next_nairobi_day(client, eleven_restaurant):
    # 2026-09-19 22:00 UTC = 2026-09-20 01:00 EAT
    res = _post(client, _sale(source_id="QS-002", occurred_at="2026-09-19T22:00:00+00:00"))
    assert res.status_code == 200
    assert res.json()["nairobi_business_days"] == ["2026-09-20"]


def test_missing_id_is_400(client, eleven_restaurant):
    body = {"records": [{"occurred_at": "2026-09-19T10:00:00+03:00", "total_cents": 100}]}
    assert _post(client, body).status_code == 400


def test_naive_timestamp_is_400(client, eleven_restaurant):
    body = {"records": [{"source_id": "X", "occurred_at": "2026-09-19T10:00:00", "total_cents": 100}]}
    assert _post(client, body).status_code == 400


def test_malformed_json_400(client, eleven_restaurant):
    res = client.post(
        "/webhooks/quicksell/data",
        content=b"{nope",
        headers={"x-api-key": _KEY, "Content-Type": "application/json"},
    )
    assert res.status_code == 400


def test_payload_not_logged(client, eleven_restaurant, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    _post(client, {
        "records": [{
            "source_id": "PRIV-1",
            "occurred_at": "2026-09-19T12:00:00+03:00",
            "total_cents": 500,
            "customer_name": "Private Name",
        }],
    })
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "Private Name" not in logged
