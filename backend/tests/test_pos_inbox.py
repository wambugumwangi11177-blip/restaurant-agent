"""Isolated synthetic receipts: raw durability, replay, scopes and compatibility."""
import json
import pytest
import auth
from fastapi import HTTPException
from integration import inbox, quicksell
from integration.inbox_models import PosInbox, PosAppliedRecord, PosParseAttempt, PosSourceBinding
from integration.models import MirrorEvent
from models import Order, Restaurant, Role, StaffRole, Tenant, User
from tests.test_quicksell_webhook import (eleven_restaurant, _mirror_tables,
                                        _quicksell_key, _post, _sale)


@pytest.fixture(autouse=True)
def durable(monkeypatch):
    monkeypatch.setenv("QUICKSELL_DURABLE_INBOX_ENABLED", "true")


def headers(user):
    return {"Authorization": "Bearer " + auth.create_access_token({"sub": user.email, "ver": 0})}


def owner(db):
    return db.query(User).filter_by(email="eleven-owner@example.test").one()


def test_original_envelope_survives_parser_failure(client, db_session, eleven_restaurant, monkeypatch, caplog):
    raw = '{ "entity": "sale", "private_wrapper": "private_customer", "records": [{"source_id":"S1","total":12.25}] }'
    original = quicksell.maybe_apply_sale
    def broken(*args, **kwargs):
        raise RuntimeError("private_customer must not leak")
    monkeypatch.setattr(quicksell, "maybe_apply_sale", broken)
    response = client.post("/webhooks/quicksell/data", content=raw,
                           headers={"x-api-key": "test-quicksell-key"})
    assert response.status_code == 200
    assert response.json()["status"] == "stored"
    assert response.json()["parse_status"] == "failed"
    receipt = db_session.query(PosInbox).one()
    assert receipt.raw_body == raw
    assert receipt.error_code == "mapping_failed"
    assert db_session.query(Order).count() == 0
    assert db_session.query(MirrorEvent).count() == 0
    assert "private_customer" not in caplog.text
    monkeypatch.setattr(quicksell, "maybe_apply_sale", original)
    path = f"/api/v1/pos/quicksell/receipts/{receipt.id}/replay"
    response = client.post(path, headers=headers(owner(db_session)))
    assert response.status_code == 200
    assert response.json()["orders_inserted"] == 1
    assert db_session.query(Order).one().total == 1225
    assert client.post(path, headers=headers(owner(db_session))).status_code == 200
    assert db_session.query(Order).count() == 1
    assert db_session.query(PosAppliedRecord).count() == 1
    attempts = db_session.query(PosParseAttempt).order_by(PosParseAttempt.id).all()
    assert [a.outcome for a in attempts] == ["failed", "parsed"]
    assert attempts[1].actor_id == owner(db_session).id


def test_unknown_envelope_is_not_a_sale(client, db_session, eleven_restaurant):
    response = _post(client, {"test": True, "records": [{"sku": "unmapped"}]})
    assert response.status_code == 200
    assert response.json()["parse_status"] == "unrecognized"
    assert db_session.query(Order).count() == 0
    status = client.get("/api/v1/pos/quicksell/status", headers=headers(owner(db_session))).json()
    assert status["receipts"] == 1 and status["backlog"] == 1
    assert status["last_receipt_at"] and status["last_successful_parse_at"] is None
    assert status["sales_live"] is None


def test_retry_records_deliveries_but_creates_one_order(client, db_session, eleven_restaurant):
    for _ in range(2):
        assert _post(client, _sale()).status_code == 200
    assert db_session.query(PosInbox).count() == 2
    assert db_session.query(PosAppliedRecord).count() == 1
    assert db_session.query(Order).count() == 1


def test_batch_failure_is_atomic_but_receipt_survives(client, db_session, eleven_restaurant):
    response = _post(client, {"entity": "sale", "records": [
        {"id": "valid", "total": "1.25"}, {"id": "invalid", "total": "not a number"}]})
    assert response.json()["parse_status"] == "failed"
    assert db_session.query(Order).count() == 0
    assert db_session.query(MirrorEvent).count() == 0
    assert db_session.query(PosAppliedRecord).count() == 0
    assert db_session.query(PosInbox).one().raw_body


def test_no_auth_no_receipt(client, db_session, eleven_restaurant):
    assert _post(client, _sale(), key="bad").status_code == 401
    assert db_session.query(PosInbox).count() == 0
    assert db_session.query(PosSourceBinding).count() == 0


def test_tenant_and_role_scopes(client, db_session, eleven_restaurant):
    receipt_id = _post(client, _sale()).json()["receipt_id"]
    tenant = Tenant(name="Other")
    db_session.add(tenant); db_session.flush()
    other = User(tenant_id=tenant.id, email="other@example.test", hashed_password="unused", role=Role.ADMIN)
    restaurant = Restaurant(tenant_id=tenant.id, name="Other")
    staff = User(tenant_id=eleven_restaurant.tenant_id, email="staff@example.test", hashed_password="unused", role=Role.STAFF, staff_role=StaffRole.STOCKKEEPER)
    db_session.add_all([other, restaurant, staff]); db_session.commit()
    base = "/api/v1/pos/quicksell"
    assert client.get(base + "/receipts", headers=headers(other)).json() == []
    assert client.get(base + "/status", headers=headers(other)).json()["receipts"] == 0
    assert client.post(base + f"/receipts/{receipt_id}/replay", headers=headers(other)).status_code == 404
    assert client.get(base + f"/receipts/{receipt_id}/attempts", headers=headers(other)).status_code == 404
    assert client.get(base + "/receipts", headers=headers(staff)).status_code == 403
    assert client.post(base + f"/receipts/{receipt_id}/replay", headers=headers(staff)).status_code == 403
    assert client.get(base + "/status").status_code == 401
    data = client.get(base + "/receipts", headers=headers(owner(db_session))).json()
    assert len(data) == 1
    assert "raw_body" not in data[0] and "result" not in data[0]


def test_status_get_does_not_provision_source(client, db_session, eleven_restaurant):
    result = client.get("/api/v1/pos/quicksell/status", headers=headers(owner(db_session)))
    assert result.status_code == 200 and result.json()["source_bound"] is False
    assert db_session.query(PosSourceBinding).count() == 0
    assert db_session.query(PosInbox).count() == 0


def test_persisted_binding_survives_restaurant_rename(client, db_session, eleven_restaurant):
    assert _post(client, _sale()).status_code == 200
    eleven_restaurant.name = "Renamed"
    db_session.commit()
    assert _post(client, _sale("second")).status_code == 200
    assert db_session.query(Order).count() == 2


def test_ambiguous_initial_binding_fails_closed(client, db_session, eleven_restaurant):
    other = Tenant(name="Another tenant")
    db_session.add(other); db_session.flush()
    db_session.add(Restaurant(tenant_id=other.id, name="Eleven")); db_session.commit()
    assert _post(client, _sale()).status_code == 503
    assert db_session.query(PosInbox).count() == 0


@pytest.mark.parametrize("raw,code", [(b'{bad', 400),
    (b'{"a":NaN}', 400), (b'{"a":Infinity}', 400),
    (b'[' * 40 + b'0' + b']' * 40, 413),
    (b'"' + b'x' * inbox.MAX_BYTES + b'"', 413)])
def test_bounded_json(raw, code):
    with pytest.raises(HTTPException) as exc:
        inbox.decode_body(raw)
    assert exc.value.status_code == code


def test_batch_limit():
    with pytest.raises(HTTPException) as exc:
        inbox.decode_body(json.dumps({"records": [{"id": i} for i in range(501)]}).encode())
    assert exc.value.status_code == 413


def test_unknown_can_be_replayed_after_adapter_improvement(client, db_session, eleven_restaurant, monkeypatch):
    payload = {"entity": "vendor_sale", "records": [{"id": "later-mapping", "total": 12}]}
    receipt_id = _post(client, payload).json()["receipt_id"]
    assert db_session.query(Order).count() == 0
    original = quicksell.is_mappable_sale
    monkeypatch.setattr(quicksell, "is_mappable_sale", lambda record, ent: ent == "vendor_sale" or original(record, ent))
    path = f"/api/v1/pos/quicksell/receipts/{receipt_id}/replay"
    result = client.post(path, headers=headers(owner(db_session)))
    assert result.json()["parse_status"] == "parsed"
    assert db_session.query(Order).count() == 1


def test_ordered_revisions_and_old_retry(client, db_session, eleven_restaurant):
    def body(version, total):
        return {"entity": "sale", "records": [{"id": "revision", "version": version, "total": total}]}
    for version, total in [(1, 10), (3, 30), (2, 20), (1, 10)]:
        assert _post(client, body(version, total)).status_code == 200
    db_session.expire_all()
    assert db_session.query(Order).one().total == 3000


def test_unknown_revision_order_needs_review(client, db_session, eleven_restaurant):
    assert _post(client, {"id": "revision", "total": 10}).json()["parse_status"] == "parsed"
    assert _post(client, {"id": "revision", "total": 20}).json()["parse_status"] == "failed"
    db_session.expire_all()
    assert db_session.query(Order).one().total == 1000
    assert db_session.query(PosInbox).filter_by(status="failed").one().error_code == "revision_order_unknown"


def test_void_is_retained_for_review_not_counted_as_sale(client, db_session, eleven_restaurant):
    result = _post(client, {"entity": "sale", "records": [{"id": "voided", "total": 10, "status": "voided"}]})
    assert result.json()["parse_status"] == "failed"
    assert db_session.query(Order).count() == 0
    assert db_session.query(PosInbox).one().error_code == "adjustment_needs_adapter"


def test_reused_version_with_different_payload_is_not_silently_dropped(client, db_session, eleven_restaurant):
    assert _post(client, {"id": "same", "version": "1", "total": 10}).json()["parse_status"] == "parsed"
    assert _post(client, {"id": "same", "version": "1", "total": 20}).json()["parse_status"] == "failed"
    db_session.expire_all()
    assert db_session.query(Order).one().total == 1000
    assert db_session.query(PosInbox).filter_by(status="failed").one().error_code == "identity_payload_conflict"


def test_failed_raw_commit_is_not_acknowledged(client, db_session, eleven_restaurant, monkeypatch):
    from sqlalchemy.orm import Session
    original = Session.commit
    def fail_receipt_commit(self):
        if any(isinstance(row, PosInbox) for row in self.new):
            raise RuntimeError("simulated durable storage failure")
        return original(self)
    monkeypatch.setattr(Session, "commit", fail_receipt_commit)
    assert _post(client, _sale()).status_code == 503
    assert db_session.query(PosInbox).count() == 0
    assert db_session.query(Order).count() == 0


def test_duplicate_json_keys_are_retained_for_review(client, db_session, eleven_restaurant):
    raw = '{"id":"duplicate-keys","total":10,"total":20}'
    result = client.post("/webhooks/quicksell/data", content=raw,
                         headers={"x-api-key": "test-quicksell-key"})
    assert result.status_code == 200
    assert result.json()["parse_status"] == "failed"
    receipt = db_session.query(PosInbox).one()
    assert receipt.raw_body == raw and receipt.error_code == "ambiguous_json_keys"
    assert db_session.query(Order).count() == 0


@pytest.mark.parametrize("value,cents", [("1.005", 101), ("12.25", 1225), ("0", 0)])
def test_decimal_money(value, cents):
    assert quicksell.total_cents_optional({"total": value}) == cents


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", True, "1e10000"])
def test_invalid_money(value):
    with pytest.raises(ValueError):
        quicksell.total_cents_optional({"total": value})
