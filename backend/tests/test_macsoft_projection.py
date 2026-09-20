"""MacSoft push -> the owner's Home page. The tracer that was missing.

Every existing MacSoft test asserts the record reached the MIRROR. That is not
the same claim as "the owner can see it", and for most of this integration's
life the two came apart: integration/ingest.py wrote a MirrorEvent and stopped,
the mirror lives on its own declarative base, and every agent queries
models.Order / MenuItem / InventoryItem. A push returned 200, the row count
rose, and Home showed yesterday's numbers.

So these tests deliberately do NOT assert on mirror rows. They push through the
real endpoint and then read /api/v1/overview/today and the domain tables, which
is the only assertion that cannot pass while the owner sees nothing.
"""
from __future__ import annotations

import pytest

import auth
import models

_KEY = "test-macsoft-key"


@pytest.fixture(autouse=True)
def _macsoft_env(monkeypatch):
    monkeypatch.setenv("MACSOFT_API_KEY", _KEY)
    # Both are explicit by design — projection refuses to guess either. See
    # integration/projection.py's module docstring.
    monkeypatch.setenv("MACSOFT_RESTAURANT_ID", "501")
    monkeypatch.setenv("MACSOFT_MONEY_UNIT", "shillings")
    # No module reload: integration/projection.py reads its config at call time
    # precisely so tests never have to. Reloading routers.webhooks leaves the
    # already-built FastAPI app holding the old handler objects, which broke two
    # unrelated M-Pesa tests when this file first did it.
    yield


@pytest.fixture(autouse=True)
def _mirror_tables(db_env):
    """Mirror + projection tables are on integration/models.py's own Base, so
    database.init_db() does not create them; alembic 046/048 do in production."""
    import database
    from integration.models import Base as IntegrationBase
    IntegrationBase.metadata.create_all(bind=database.engine)


@pytest.fixture
def owner(db_session):
    db = db_session
    db.add(models.Tenant(id=401, name="Vibanda Village"))
    db.flush()
    db.add(models.Restaurant(id=501, tenant_id=401, name="Vibanda Village"))
    db.flush()
    user = models.User(tenant_id=401, active_restaurant_id=501,
                       email="owner@vibanda.test", hashed_password="unused",
                       role=models.Role.ADMIN)
    db.add(user)
    db.commit()
    token = auth.create_access_token({"sub": user.email})
    return user, {"Authorization": f"Bearer {token}"}


def _push(client, body, key=_KEY):
    headers = {"x-api-key": key} if key is not None else {}
    return client.post("/webhooks/macsoft/data", json=body, headers=headers)


def _sale(source_id="INV-900", version=1, total="1250.50", when="2026-09-19T14:30:11+03:00"):
    return {"entity": "sale", "records": [{
        "source_id": source_id, "version": version,
        "date": when, "total": total, "payment_method": "mpesa",
    }]}


# ── The claim that matters ───────────────────────────────────────────────────

def test_a_pushed_sale_becomes_revenue_the_owner_can_see(client, db_session, owner):
    """The whole point. If this passes, data pushed by MacSoft reaches Home."""
    _, headers = owner
    assert _push(client, _sale()).status_code == 200

    order = db_session.query(models.Order).filter(
        models.Order.restaurant_id == 501).one()
    assert order.total == 125050          # 1250.50 shillings -> cents
    assert order.is_paid is True          # or it is not revenue
    assert order.status == models.OrderStatus.SERVED
    assert order.payment_method == models.PaymentMethod.MPESA


def test_the_push_response_says_what_became_visible(client, owner):
    """"Stored" and "visible" are different numbers and the response says both."""
    body = _push(client, _sale()).json()
    assert body["inserted"] == 1
    assert body["projected"]["created"] == 1
    assert body["projected"]["into"] == {"orders": 1}
    assert body["projected"]["unmapped"] == 0


def test_status_reports_projection_not_just_storage(client, owner):
    _push(client, _sale())
    res = client.get("/webhooks/macsoft/status", headers={"x-api-key": _KEY})
    assert res.status_code == 200
    body = res.json()
    assert body["total_records"] == 1
    assert body["projection"]["projected"] == 1
    assert body["projection"]["by_table"] == {"orders": 1}
    # Echoed so a 100x scaling error is caught against a real invoice.
    assert body["projection"]["money_unit"] == "shillings"


# ── Idempotency and correction ───────────────────────────────────────────────

def test_resending_the_same_sale_does_not_double_revenue(client, db_session, owner):
    _push(client, _sale())
    _push(client, _sale())
    orders = db_session.query(models.Order).filter(
        models.Order.restaurant_id == 501).all()
    assert len(orders) == 1
    assert orders[0].total == 125050


def test_a_corrected_sale_updates_in_place(client, db_session, owner):
    _push(client, _sale(total="1250.50", version=1))
    _push(client, _sale(total="900.00", version=2))
    orders = db_session.query(models.Order).filter(
        models.Order.restaurant_id == 501).all()
    assert len(orders) == 1, "a correction must not create a second order"
    assert orders[0].total == 90000


# ── Money ────────────────────────────────────────────────────────────────────

def test_cents_unit_is_honoured(client, db_session, owner, monkeypatch):
    monkeypatch.setenv("MACSOFT_MONEY_UNIT", "cents")
    _push(client, _sale(total=125050))
    order = db_session.query(models.Order).filter(
        models.Order.restaurant_id == 501).one()
    assert order.total == 125050


def test_a_negative_total_is_refused_not_clamped(client, db_session, owner):
    """orders.total carries a >= 0 CheckConstraint; a clamp would hide a refund
    as a zero sale, and letting it through would fail the whole batch."""
    body = _push(client, _sale(total="-40.00")).json()
    assert body["projected"]["unmapped"] == 1
    assert db_session.query(models.Order).count() == 0


# ── Menu and inventory ───────────────────────────────────────────────────────

def test_a_pushed_menu_item_becomes_a_dish_with_its_cost(client, db_session, owner):
    _push(client, {"entity": "product", "records": [{
        "source_id": "SKU-1", "version": 1, "name": "Nyama Choma",
        "price": "850.00", "cost_price": "380.00", "category": "Grill",
    }]})
    item = db_session.query(models.MenuItem).filter(
        models.MenuItem.restaurant_id == 501).one()
    assert (item.name, item.price, item.cost_price) == ("Nyama Choma", 85000, 38000)


def test_a_later_push_without_a_cost_does_not_zero_the_cost(client, db_session, owner):
    """A zero cost_price reads as a 100% margin in ai/profit/intelligence.py:181
    and is skipped by its leak detection — so omission must never overwrite."""
    _push(client, {"entity": "product", "records": [{
        "source_id": "SKU-1", "version": 1, "name": "Ugali",
        "price": "150.00", "cost_price": "60.00",
    }]})
    _push(client, {"entity": "product", "records": [{
        "source_id": "SKU-1", "version": 2, "name": "Ugali", "price": "170.00",
    }]})
    item = db_session.query(models.MenuItem).filter_by(restaurant_id=501).one()
    assert item.price == 17000
    assert item.cost_price == 6000


def test_a_pushed_stock_level_reaches_the_home_low_stock_card(client, db_session, owner):
    _, headers = owner
    db_session.add(models.InventoryItem(restaurant_id=501, item_name="Beef",
                                        quantity=50, unit="kg",
                                        low_stock_threshold=10))
    db_session.commit()
    _push(client, {"entity": "stock", "records": [{
        "source_id": "ITEM-7", "version": 1, "name": "Beef",
        "quantity": 2, "unit": "kg",
    }]})
    feed = client.get("/api/v1/overview/today", headers=headers).json()
    assert [row["name"] for row in feed["stock"]["low_stock"]] == ["Beef"]
    assert any("Beef" in card["title"] for card in feed["attention"])


def test_an_existing_dish_is_matched_by_name_not_duplicated(client, db_session, owner):
    db_session.add(models.MenuItem(restaurant_id=501, name="Pilau",
                                   price=50000, cost_price=20000))
    db_session.commit()
    _push(client, {"entity": "product", "records": [{
        "source_id": "SKU-9", "version": 1, "name": "Pilau", "price": "600.00",
    }]})
    items = db_session.query(models.MenuItem).filter_by(restaurant_id=501).all()
    assert len(items) == 1
    assert items[0].price == 60000


# ── Refusing to guess ────────────────────────────────────────────────────────

def test_an_unrecognisable_record_is_reported_not_forced(client, db_session, owner):
    body = _push(client, {"entity": "mystery", "records": [{
        "source_id": "X-1", "version": 1, "colour": "blue",
    }]}).json()
    assert body["inserted"] == 1, "it must still be mirrored"
    assert body["projected"]["unmapped"] == 1
    assert body["projected"]["created"] == 0
    assert body["projected"]["unmapped_reasons"]
    assert db_session.query(models.Order).count() == 0


def test_an_unresolvable_restaurant_refuses_rather_than_picking_one(
        client, db_session, owner, monkeypatch):
    """A day of sales attached to the wrong restaurant is silent and
    unrecoverable, so ambiguity is refused and reported."""
    monkeypatch.setenv("MACSOFT_RESTAURANT_ID", "9999")
    body = _push(client, _sale()).json()
    assert body["inserted"] == 1
    assert body["projected"]["unmapped"] == 1
    assert db_session.query(models.Order).count() == 0


# ── Re-projection ────────────────────────────────────────────────────────────

def test_reproject_recovers_records_an_earlier_mapping_missed(client, db_session, owner):
    """The property that makes shipping before seeing MacSoft's real payload
    safe: the mirror keeps everything, so widening the mapping and re-running
    picks up what the first pass could not place."""
    from integration import projection
    from integration.models import SourceSystem

    _push(client, {"entity": "sale", "records": [{
        "source_id": "ODD-1", "version": 1,
        "grand_total_kes": "500.00", "date": "2026-09-19",
    }]})
    assert db_session.query(models.Order).count() == 0, "unknown field name, as expected"

    # Learn the real field name and re-run — exactly what happens once MacSoft's
    # export has been seen.
    projection._TOTAL_KEYS = projection._TOTAL_KEYS + ("grand_total_kes",)
    source = db_session.query(SourceSystem).filter(
        SourceSystem.slug == "macsoft-prod").one()
    result = projection.reproject_all(db_session, source.id)

    assert result["projected"] == 1
    order = db_session.query(models.Order).filter_by(restaurant_id=501).one()
    assert order.total == 50000
