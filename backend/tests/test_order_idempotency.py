"""
Order create idempotency (client_order_id) — the backend half of offline POS.

The offline queue (frontend lib/offlineQueue.ts) can't always tell whether a
queued order it's flushing actually reached the server: the request may have
succeeded and only the RESPONSE was lost to a flaky connection, in which case
a naive retry would ring the same ticket into the kitchen twice and deduct its
stock twice. Attaching a client-generated UUID and treating a repeat of the
same id as "already placed" — return the existing order, do nothing else — is
what makes retrying safe.

These tests pin the two things that make that trustworthy: a genuine replay is
a true no-op (no duplicate row, no second stock deduction, no second kitchen
timer), and a normal online order — which never sends a client_order_id — is
completely unaffected.
"""

import uuid

import auth
import models


def _owner(db_session, suffix):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id, email=f"idem{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN,
        token_version=0,
    )
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add_all([user, restaurant])
    db_session.commit()
    return auth.create_access_token({"sub": user.email, "ver": 0}), restaurant.id


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _dish(db_session, restaurant_id, price=1000):
    item = models.MenuItem(restaurant_id=restaurant_id, name="Ugali", price=price, category="main")
    db_session.add(item)
    db_session.commit()
    return item.id


# ── Authenticated POS path ───────────────────────────────────────────────────

def test_replaying_the_same_client_order_id_returns_the_same_order(client, db_session):
    token, rid = _owner(db_session, "replay")
    dish = _dish(db_session, rid)
    cid = str(uuid.uuid4())

    first = client.post("/orders/", headers=_hdr(token), json={
        "items": [{"menu_item_id": dish, "quantity": 2}],
        "client_order_id": cid,
    })
    assert first.status_code == 200
    second = client.post("/orders/", headers=_hdr(token), json={
        "items": [{"menu_item_id": dish, "quantity": 2}],
        "client_order_id": cid,
    })
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert db_session.query(models.Order).count() == 1


def test_replay_does_not_double_deduct_stock(client, db_session):
    token, rid = _owner(db_session, "stock")
    inv = models.InventoryItem(restaurant_id=rid, item_name="Maize Flour", quantity=10.0, unit="kg", low_stock_threshold=1)
    db_session.add(inv)
    db_session.commit()
    dish = _dish(db_session, rid)
    db_session.add(models.MenuIngredient(menu_item_id=dish, inventory_item_id=inv.id, quantity_per_serving=1.0))
    db_session.commit()

    cid = str(uuid.uuid4())
    for _ in range(3):
        r = client.post("/orders/", headers=_hdr(token), json={
            "items": [{"menu_item_id": dish, "quantity": 1}],
            "client_order_id": cid,
        })
        assert r.status_code == 200

    db_session.expire_all()
    assert db_session.get(models.InventoryItem, inv.id).quantity == 9.0   # deducted once, not three times


def test_replay_does_not_duplicate_prep_timers(client, db_session):
    """Guards the KDS side of the same replay: a retried create must not
    leave two PrepTime rows once the kitchen starts the ticket."""
    token, rid = _owner(db_session, "prep")
    dish = _dish(db_session, rid)
    cid = str(uuid.uuid4())

    r1 = client.post("/orders/", headers=_hdr(token), json={
        "items": [{"menu_item_id": dish, "quantity": 1}], "client_order_id": cid,
    })
    order_id = r1.json()["id"]
    client.post("/orders/", headers=_hdr(token), json={          # replay
        "items": [{"menu_item_id": dish, "quantity": 1}], "client_order_id": cid,
    })

    client.patch(f"/orders/{order_id}/status", headers=_hdr(token), json={"status": "prep"})
    assert db_session.query(models.PrepTime).count() == 1


def test_different_client_order_ids_create_separate_orders(client, db_session):
    """The whole point of a UUID per queued order — two genuinely different
    tickets must never collapse into one just because they arrived close
    together during a sync flush."""
    token, rid = _owner(db_session, "distinct")
    dish = _dish(db_session, rid)

    client.post("/orders/", headers=_hdr(token), json={
        "items": [{"menu_item_id": dish, "quantity": 1}], "client_order_id": str(uuid.uuid4()),
    })
    client.post("/orders/", headers=_hdr(token), json={
        "items": [{"menu_item_id": dish, "quantity": 1}], "client_order_id": str(uuid.uuid4()),
    })
    assert db_session.query(models.Order).count() == 2


def test_ordinary_online_orders_are_unaffected(client, db_session):
    """No client_order_id is the normal path — every existing POS/web order.
    Placing several with none set must behave exactly as before: independent
    orders, never collapsed into each other."""
    token, rid = _owner(db_session, "normal")
    dish = _dish(db_session, rid)

    for _ in range(3):
        r = client.post("/orders/", headers=_hdr(token), json={
            "items": [{"menu_item_id": dish, "quantity": 1}],
        })
        assert r.status_code == 200
    assert db_session.query(models.Order).count() == 3


def test_client_order_id_is_scoped_per_restaurant(client, db_session):
    """Two different restaurants' offline queues could theoretically reuse an
    id (astronomically unlikely with a real UUID, but the constraint should
    not assume that) — the same id must never collide across tenants."""
    token_a, rid_a = _owner(db_session, "ta")
    token_b, rid_b = _owner(db_session, "tb")
    dish_a = _dish(db_session, rid_a)
    dish_b = _dish(db_session, rid_b)

    cid = str(uuid.uuid4())
    a = client.post("/orders/", headers=_hdr(token_a), json={
        "items": [{"menu_item_id": dish_a, "quantity": 1}], "client_order_id": cid,
    })
    b = client.post("/orders/", headers=_hdr(token_b), json={
        "items": [{"menu_item_id": dish_b, "quantity": 1}], "client_order_id": cid,
    })
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["id"] != b.json()["id"]


# ── Public (customer self-service) path ──────────────────────────────────────

def test_public_order_replay_is_also_idempotent(client, db_session):
    token, rid = _owner(db_session, "public")
    dish = _dish(db_session, rid)
    cid = str(uuid.uuid4())

    for _ in range(2):
        r = client.post(f"/orders/public?restaurant_id={rid}", json={
            "items": [{"menu_item_id": dish, "quantity": 1}],
            "order_type": "takeout",
            "client_order_id": cid,
        })
        assert r.status_code == 200
    assert db_session.query(models.Order).count() == 1
