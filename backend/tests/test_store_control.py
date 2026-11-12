"""Chef PIN, handover, spoilage, day close, and the append-only guards."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, inspect, text

import models
from money_visibility import money_keys_in
from tests.test_store_intake import JPEG, _unlock
from tests.test_storekeeper_foundation import _add_staff, _auth, _tenant, _token

PIN = "1357"


def _load(name):
    path = Path(__file__).parents[1] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _chef(client, jack, name="Asha", pin=PIN, photo=False):
    files = {"photo": ("chef.jpg", JPEG, "image/jpeg")} if photo else None
    response = client.post(
        "/api/v1/store/chefs",
        headers=_auth(_token(jack)),
        data={"name": name, "pin": pin},
        files=files,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _open(client, owner, name, quantity, unit="kg", zone="Main store"):
    response = client.post(
        "/api/v1/store/items/opening",
        headers=_auth(_token(owner)),
        json={"item_name": name, "quantity": quantity, "unit": unit, "zone": zone},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_owner_or_jack_adds_a_chef_who_cannot_log_in(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-chef@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-chef@eleven.leviii", models.StaffRole.STOCKKEEPER)
    cook = _add_staff(db_session, tenant, restaurant, "cook-chef@eleven.leviii", models.StaffRole.KITCHEN)
    _unlock(client, jack)
    before = db_session.query(models.User).count()
    blocked = client.post(
        "/api/v1/store/chefs",
        headers=_auth(_token(cook)),
        data={"name": "Asha", "pin": PIN},
    )
    assert blocked.status_code == 403
    bad = client.post(
        "/api/v1/store/chefs",
        headers=_auth(_token(jack)),
        data={"name": "Asha", "pin": "12345"},
    )
    assert bad.status_code == 400
    created = _chef(client, jack, photo=True)
    assert created["name"] == "Asha"
    assert created["created_by"] == jack.email
    assert created["created_at"]
    assert "hashed_pin" not in created
    assert db_session.query(models.User).count() == before
    photo = client.get(f"/api/v1/store/chefs/{created['id']}/photo", headers=_auth(_token(jack)))
    assert photo.status_code == 200
    hidden = client.get(f"/api/v1/store/chefs/{created['id']}/photo", headers=_auth(_token(cook)))
    assert hidden.status_code == 403
    owner_added = client.post(
        "/api/v1/store/chefs",
        headers=_auth(_token(owner)),
        data={"name": "Bea", "pin": "2468"},
    )
    assert owner_added.status_code == 201
    listed = client.get("/api/v1/store/chefs", headers=_auth(_token(jack))).json()["chefs"]
    assert [row["name"] for row in listed] == ["Asha", "Bea"]
    assert money_keys_in(listed) == []
    audit = db_session.query(models.StaffEntryAudit).filter_by(action="chef_added").first()
    assert audit.user_id == jack.id
    assert audit.created_at is not None
    assert PIN not in audit.summary
    assert PIN not in (audit.detail_json or "")


def test_five_wrong_pins_lock_the_chef_for_fifteen_minutes(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-pin@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-pin@eleven.leviii", models.StaffRole.STOCKKEEPER)
    _unlock(client, jack)
    _open(client, owner, "Rice", 6)
    chef = _chef(client, jack)
    item_id = client.get("/api/v1/store/items", headers=_auth(_token(jack))).json()["items"][0]["id"]
    lines = json.dumps([{"item_id": item_id, "quantity": 1}])
    for _ in range(4):
        wrong = client.post(
            "/api/v1/store/handover",
            headers=_auth(_token(jack)),
            data={"lines": lines, "chef_id": str(chef["id"]), "pin": "0000"},
        )
        assert wrong.status_code == 400, wrong.text
        assert wrong.json()["detail"] == "That PIN is wrong."
    locked = client.post(
        "/api/v1/store/handover",
        headers=_auth(_token(jack)),
        data={"lines": lines, "chef_id": str(chef["id"]), "pin": "0000"},
    )
    assert locked.status_code == 423, locked.text
    still = client.post(
        "/api/v1/store/handover",
        headers=_auth(_token(jack)),
        data={"lines": lines, "chef_id": str(chef["id"]), "pin": PIN},
    )
    assert still.status_code == 423
    db_session.expire_all()
    row = db_session.query(models.StoreChef).filter_by(id=chef["id"]).one()
    assert row.failed_pin_attempts == 5
    assert row.pin_locked_until is not None
    audits = db_session.query(models.StaffEntryAudit).filter(
        models.StaffEntryAudit.action.in_(("chef_pin_failed", "chef_pin_locked"))
    ).all()
    assert audits
    blob = " ".join(f"{item.summary} {item.detail_json}" for item in audits)
    assert "0000" not in blob
    assert PIN not in blob
    rice = db_session.query(models.InventoryItem).filter_by(item_name="Rice").one()
    assert rice.quantity == 6


def test_handover_moves_stock_and_the_photo_note_stays_with_the_owner(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-hand@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-hand@eleven.leviii", models.StaffRole.STOCKKEEPER)
    cook = _add_staff(db_session, tenant, restaurant, "cook-hand@eleven.leviii", models.StaffRole.KITCHEN)
    _unlock(client, jack)
    _open(client, owner, "Rice", 10)
    chef = _chef(client, jack)
    item_id = client.get("/api/v1/store/items", headers=_auth(_token(jack))).json()["items"][0]["id"]
    explained = {
        "note": "The photo matches 2 kg of Rice.",
        "match": True,
        "mismatches": [],
        "model": "deepseek/deepseek-v4-flash",
        "fell_back": False,
        "ungrounded": [],
    }
    with patch("store_vision.ask_model", return_value={"goods_items": [{"name": "Rice", "quantity": 2}]}), patch(
        "store_vision.explain_difference", return_value=explained
    ):
        saved = client.post(
            "/api/v1/store/handover",
            headers=_auth(_token(jack)),
            data={"lines": json.dumps([{"item_id": item_id, "quantity": 2}]), "chef_id": str(chef["id"]), "pin": PIN},
            files={"photo": ("goods.jpg", JPEG, "image/jpeg")},
        )
    assert saved.status_code == 201, saved.text
    assert saved.json()["ai"] == {"label": "AI", "status": "pending"}
    assert "note" not in saved.json()["ai"]
    assert money_keys_in(saved.json()) == []
    assert "http" not in json.dumps(saved.json())
    db_session.expire_all()
    rice = db_session.query(models.InventoryItem).filter_by(item_name="Rice").one()
    assert rice.quantity == 10
    kitchen = (
        db_session.query(models.StockBalance)
        .join(models.StockZone, models.StockZone.id == models.StockBalance.zone_id)
        .filter(models.StockZone.name == "Kitchen", models.StockBalance.inventory_item_id == rice.id)
        .one()
    )
    assert kitchen.quantity == 2
    jack_view = client.get("/api/v1/store/handovers", headers=_auth(_token(jack))).json()["handovers"][0]
    assert jack_view["ai"]["status"] == "match"
    assert "note" not in jack_view["ai"]
    assert "mismatches" not in jack_view["ai"]
    owner_view = client.get("/api/v1/store/handovers", headers=_auth(_token(owner))).json()["handovers"][0]
    assert owner_view["ai"]["label"] == "AI"
    assert owner_view["ai"]["note"] == "The photo matches 2 kg of Rice."
    assert owner_view["created_by"] == jack.email
    photo = client.get(
        f"/api/v1/store/handovers/{saved.json()['id']}/photo",
        headers=_auth(_token(jack)),
    )
    assert photo.status_code == 200
    assert client.get(
        f"/api/v1/store/handovers/{saved.json()['id']}/photo",
        headers=_auth(_token(cook)),
    ).status_code == 403
    notes = db_session.query(models.Notification).all()
    assert all("AI" not in f"{note.title} {note.body}" for note in notes)
    feed = client.get("/api/v1/staff-setup/activity", headers=_auth(_token(owner))).json()["entries"]
    assert any(entry["action"] == "kitchen_handover" and entry["email"] == jack.email and entry["at"] for entry in feed)
    assert any(entry["action"] == "handover_ai_match" and entry["summary"].startswith("AI:") for entry in feed)


def test_a_failed_photo_read_does_not_call_the_text_model_or_block_the_handover(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-fail@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-fail@eleven.leviii", models.StaffRole.STOCKKEEPER)
    _unlock(client, jack)
    _open(client, owner, "Rice", 4)
    chef = _chef(client, jack)
    item_id = client.get("/api/v1/store/items", headers=_auth(_token(jack))).json()["items"][0]["id"]
    with patch("store_vision.ask_model", side_effect=RuntimeError("down")), patch("store_vision.explain_difference") as explain:
        saved = client.post(
            "/api/v1/store/handover",
            headers=_auth(_token(jack)),
            data={"lines": json.dumps([{"item_id": item_id, "quantity": 1}]), "chef_id": str(chef["id"]), "pin": PIN},
            files={"photo": ("goods.jpg", JPEG, "image/jpeg")},
        )
    assert saved.status_code == 201, saved.text
    assert explain.call_count == 0
    owner_view = client.get("/api/v1/store/handovers", headers=_auth(_token(owner))).json()["handovers"][0]
    assert owner_view["ai"]["status"] == "unavailable"
    assert owner_view["ai"]["note"] == "AI check unavailable"
    jack_view = client.get("/api/v1/store/handovers", headers=_auth(_token(jack))).json()["handovers"][0]
    assert jack_view["ai"] == {"label": "AI", "status": "unavailable"}


def test_spoilage_drops_stock_and_a_large_loss_waits_for_the_owner(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-spoil@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-spoil@eleven.leviii", models.StaffRole.STOCKKEEPER)
    cook = _add_staff(db_session, tenant, restaurant, "cook-spoil@eleven.leviii", models.StaffRole.KITCHEN)
    _unlock(client, jack)
    _open(client, owner, "Rice", 10)
    chef = _chef(client, jack)
    item_id = client.get("/api/v1/store/items", headers=_auth(_token(jack))).json()["items"][0]["id"]

    def post(quantity, reason="spoiled", text=""):
        return client.post(
            "/api/v1/store/spoilage",
            headers=_auth(_token(jack)),
            data={
                "item_id": str(item_id),
                "quantity": str(quantity),
                "zone": "Main store",
                "reason_code": reason,
                "reason_text": text,
                "chef_id": str(chef["id"]),
                "pin": PIN,
            },
            files={"photo": ("waste.jpg", JPEG, "image/jpeg")},
        )

    small = post(1)
    assert small.status_code == 201, small.text
    assert small.json()["status"] == "reported"
    assert small.json()["message"] == "Saved."
    assert money_keys_in(small.json()) == []
    large = post(5, "other", "The sack split")
    assert large.status_code == 201, large.text
    assert large.json()["status"] == "needs_approval"
    missing = client.post(
        "/api/v1/store/spoilage",
        headers=_auth(_token(jack)),
        data={
            "item_id": str(item_id),
            "quantity": "1",
            "reason_code": "spoiled",
            "chef_id": str(chef["id"]),
            "pin": PIN,
        },
    )
    assert missing.status_code == 422
    assert client.post(
        "/api/v1/store/spoilage",
        headers=_auth(_token(cook)),
        data={"item_id": str(item_id), "quantity": "1", "reason_code": "spoiled", "chef_id": str(chef["id"]), "pin": PIN},
        files={"photo": ("waste.jpg", JPEG, "image/jpeg")},
    ).status_code == 403
    db_session.expire_all()
    assert db_session.query(models.InventoryItem).filter_by(item_name="Rice").one().quantity == 4
    jack_queue = client.get("/api/v1/store/approvals", headers=_auth(_token(jack)))
    assert jack_queue.status_code == 403
    pending = client.get("/api/v1/store/approvals", headers=_auth(_token(owner))).json()["pending"]
    assert len(pending) == 1
    assert pending[0]["kind"] == "spoilage"
    assert pending[0]["quantity"] == 5
    approved = client.post(
        "/api/v1/store/approvals",
        headers=_auth(_token(owner)),
        json={"kind": "spoilage", "id": large.json()["id"]},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved_by"] == owner.email
    assert approved.json()["approved_at"]
    feed = client.get("/api/v1/staff-setup/activity", headers=_auth(_token(owner))).json()["entries"]
    assert any(entry["action"] == "spoilage_recorded" for entry in feed)
    assert any(entry["action"] == "spoilage_approved" for entry in feed)


def test_close_shows_a_quantity_difference_and_marks_working_alone(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-close@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-close@eleven.leviii", models.StaffRole.STOCKKEEPER)
    _unlock(client, jack)
    rice = _open(client, owner, "Rice", 8)
    oil = _open(client, owner, "Oil", 2, unit="litre")
    chef = _chef(client, jack)
    expected = client.get("/api/v1/store/close/expected", headers=_auth(_token(jack)))
    assert expected.status_code == 200
    assert money_keys_in(expected.json()) == []
    alone = client.post(
        "/api/v1/store/close",
        headers=_auth(_token(jack)),
        json={
            "working_alone": True,
            "lines": [
                {"item_id": rice["id"], "counted_qty": 8},
                {"item_id": oil["id"], "counted_qty": 2},
            ],
        },
    )
    assert alone.status_code == 201, alone.text
    assert alone.json()["working_alone"] is True
    assert alone.json()["status"] == "reported"
    assert alone.json()["message"] == "Saved."
    assert money_keys_in(alone.json()) == []
    short = client.post(
        "/api/v1/store/close",
        headers=_auth(_token(jack)),
        json={
            "working_alone": False,
            "chef_id": chef["id"],
            "pin": PIN,
            "lines": [
                {"item_id": rice["id"], "counted_qty": 7},
                {"item_id": oil["id"], "counted_qty": 2},
            ],
        },
    )
    assert short.status_code == 201, short.text
    assert short.json()["status"] == "needs_approval"
    rice_line = next(line for line in short.json()["lines"] if line["item_name"] == "Rice")
    assert rice_line["difference"] == -1
    assert "cost" not in json.dumps(short.json())
    both = client.post(
        "/api/v1/store/close",
        headers=_auth(_token(jack)),
        json={"working_alone": True, "chef_id": chef["id"], "pin": PIN, "lines": []},
    )
    assert both.status_code == 400
    owner_view = client.get("/api/v1/store/approvals", headers=_auth(_token(owner))).json()
    alone_event = next(item for item in owner_view["events"] if item["kind"] == "close" and item["working_alone"])
    assert alone_event["working_alone"] is True
    pending = [item for item in owner_view["pending"] if item["kind"] == "close"]
    assert len(pending) == 1
    approved = client.post(
        "/api/v1/store/approvals",
        headers=_auth(_token(owner)),
        json={"kind": "close", "id": short.json()["id"]},
    )
    assert approved.status_code == 200
    db_session.expire_all()
    assert db_session.query(models.InventoryItem).filter_by(item_name="Rice").one().quantity == 8
    feed = client.get("/api/v1/staff-setup/activity", headers=_auth(_token(owner))).json()["entries"]
    assert any("Working alone" in entry["summary"] for entry in feed)
    assert any(entry["action"] == "day_closed" and entry["email"] == jack.email for entry in feed)


def test_control_rows_refuse_update_and_delete(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-audit@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-audit@eleven.leviii", models.StaffRole.STOCKKEEPER)
    _unlock(client, jack)
    _open(client, owner, "Rice", 3)
    chef = _chef(client, jack)
    item_id = client.get("/api/v1/store/items", headers=_auth(_token(jack))).json()["items"][0]["id"]
    saved = client.post(
        "/api/v1/store/handover",
        headers=_auth(_token(jack)),
        data={"lines": json.dumps([{"item_id": item_id, "quantity": 1}]), "chef_id": str(chef["id"]), "pin": PIN},
    )
    assert saved.status_code == 201, saved.text
    spoiled = client.post(
        "/api/v1/store/spoilage",
        headers=_auth(_token(jack)),
        data={
            "item_id": str(item_id),
            "quantity": "1",
            "zone": "Main store",
            "reason_code": "expired",
            "reason_text": "",
            "chef_id": str(chef["id"]),
            "pin": PIN,
        },
        files={"photo": ("waste.jpg", JPEG, "image/jpeg")},
    )
    assert spoiled.status_code == 201, spoiled.text
    db_session.expire_all()
    handover = db_session.query(models.KitchenHandover).one()
    handover.created_by_user_id = owner.id
    with pytest.raises(ValueError, match="append-only"):
        db_session.commit()
    db_session.rollback()
    line = db_session.query(models.KitchenHandoverLine).one()
    db_session.delete(line)
    with pytest.raises(ValueError, match="append-only"):
        db_session.commit()
    db_session.rollback()
    spoilage = db_session.query(models.SpoilageRecord).one()
    spoilage.quantity = 9
    with pytest.raises(ValueError, match="append-only"):
        db_session.commit()
    db_session.rollback()
    db_session.delete(spoilage)
    with pytest.raises(ValueError, match="append-only"):
        db_session.commit()
    db_session.rollback()
    audit = db_session.query(models.StaffEntryAudit).filter_by(action="kitchen_handover").one()
    db_session.delete(audit)
    with pytest.raises(ValueError, match="append-only"):
        db_session.commit()
    db_session.rollback()
    chef_row = db_session.query(models.StoreChef).one()
    chef_row.name = "Someone else"
    with pytest.raises(ValueError, match="append-only"):
        db_session.commit()
    db_session.rollback()


def test_jack_cannot_open_the_owner_import(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-gap@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-gap@eleven.leviii", models.StaffRole.STOCKKEEPER)
    _unlock(client, jack)
    blocked = client.get("/api/v1/eleven/import/template", headers=_auth(_token(jack)))
    assert blocked.status_code == 403
    allowed = client.get("/api/v1/eleven/import/template", headers=_auth(_token(owner)))
    assert allowed.status_code == 200


def test_j03_upgrade_is_idempotent_and_merges_with_the_pos_inbox():
    j03 = _load("j03_store_control.py")
    pos = _load("051_pos_durable_inbox.py")
    merge = _load("j04_merge_store_pos.py")
    assert j03.revision == "j03_store_control"
    assert j03.down_revision == "j02_store_intake"
    assert pos.revision == "051_pos_durable_inbox"
    assert pos.down_revision == "050_creative_takes"
    assert merge.down_revision == ("j03_store_control", "051_pos_durable_inbox")
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(engine)
    with engine.begin() as connection:
        from alembic.operations import Operations
        from alembic.runtime.migration import MigrationContext

        with Operations.context(MigrationContext.configure(connection)):
            j03.upgrade()
            pos.upgrade()
            merge.upgrade()
        names = set(inspect(connection).get_table_names())
        assert {"store_chefs", "kitchen_handovers", "spoilage_records", "day_closes", "pos_inbox"} <= names
    engine.dispose()


def test_postgres_audit_trigger_rejects_a_change():
    """The service guard covers SQLite. This checks the trigger when Postgres is the database."""
    import os

    url = os.getenv("CONTROL_POSTGRES_URL")
    if not url:
        pytest.skip("CONTROL_POSTGRES_URL is not set")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO staff_entry_audits (restaurant_id, user_id, action, entity_type, summary, detail_json, created_at) "
            "VALUES (1, 1, 'probe', 'probe', 'probe', '{}', CURRENT_TIMESTAMP)"
        ))
        row_id = connection.execute(text("SELECT id FROM staff_entry_audits WHERE action = 'probe'")).scalar()
        with pytest.raises(Exception, match="append-only"):
            connection.execute(text("UPDATE staff_entry_audits SET summary = 'changed' WHERE id = :id"), {"id": row_id})
    engine.dispose()
