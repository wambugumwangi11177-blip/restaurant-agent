"""QuickSell can target Eleven (empty) via PosSourceBinding slug + header."""
from __future__ import annotations

import pytest

import models
from auth import get_password_hash
from tests.test_quicksell_webhook import _KEY, _post


@pytest.fixture(autouse=True)
def _quicksell_key(monkeypatch):
    monkeypatch.setenv("QUICKSELL_API_KEY", _KEY)


@pytest.fixture(autouse=True)
def _mirror_tables(db_env):
    import database
    from integration.models import Base as IntegrationBase

    IntegrationBase.metadata.create_all(bind=database.engine)


def _seed_bindings(db_session):
    from integration.inbox_models import PosSourceBinding

    tenant = models.Tenant(name="Eleven")
    db_session.add(tenant)
    db_session.flush()
    demo = models.Restaurant(tenant_id=tenant.id, name="Eleven", address="")
    empty = models.Restaurant(tenant_id=tenant.id, name="Eleven (empty)", address="")
    owner = models.User(
        tenant_id=tenant.id,
        email="o@eleven.leviii",
        hashed_password=get_password_hash("Ownerpass1"),
        role=models.Role.ADMIN,
        staff_role=models.StaffRole.OWNER,
    )
    db_session.add_all([demo, empty, owner])
    db_session.flush()
    db_session.add(PosSourceBinding(slug="quicksell", restaurant_id=demo.id))
    db_session.add(PosSourceBinding(slug="quicksell-empty", restaurant_id=empty.id))
    dish = models.MenuItem(restaurant_id=empty.id, name="Pilau", category="Mains", price=50000, is_available=True)
    db_session.add(dish)
    db_session.commit()
    return demo, empty


def test_default_binding_hits_demo(client, db_session):
    demo, empty = _seed_bindings(db_session)
    body = {
        "entity": "sale",
        "records": [{
            "source_id": "DEMO-BIND-1",
            "occurred_at": "2026-09-19T12:00:00+03:00",
            "total_cents": 10000,
        }],
    }
    assert _post(client, body).status_code == 200
    assert db_session.query(models.Order).filter(models.Order.restaurant_id == demo.id).count() == 1
    assert db_session.query(models.Order).filter(models.Order.restaurant_id == empty.id).count() == 0


def test_empty_binding_header(client, db_session):
    demo, empty = _seed_bindings(db_session)
    body = {
        "entity": "sale",
        "records": [{
            "source_id": "EMPTY-BIND-1",
            "occurred_at": "2026-09-19T12:00:00+03:00",
            "total_cents": 20000,
        }],
    }
    headers = {"x-api-key": _KEY, "X-Leviii-Pos-Binding": "quicksell-empty"}
    assert client.post("/webhooks/quicksell/data", json=body, headers=headers).status_code == 200
    assert db_session.query(models.Order).filter(models.Order.restaurant_id == empty.id).count() == 1
    assert db_session.query(models.Order).filter(models.Order.restaurant_id == demo.id).count() == 0


def test_money_pnl_reflects_quicksell_sale(client, db_session):
    from auth import create_access_token
    from tests.test_storekeeper_foundation import _auth

    demo, _empty = _seed_bindings(db_session)
    owner = db_session.query(models.User).filter(models.User.email == "o@eleven.leviii").one()
    owner.active_restaurant_id = demo.id
    db_session.commit()
    body = {
        "entity": "sale",
        "records": [{
            "source_id": "PNL-SALE-1",
            "occurred_at": "2026-11-25T10:00:00+03:00",
            "total_cents": 500000,
        }],
    }
    assert _post(client, body).status_code == 200
    token = create_access_token({"sub": owner.email, "ver": owner.token_version or 0})
    pnl = client.get("/api/v1/eleven/money/pnl", headers=_auth(token))
    assert pnl.status_code == 200
    assert pnl.json().get("has_sales") is True
    assert pnl.json().get("revenue_cents", 0) >= 500000