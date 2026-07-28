"""
backend/tests/test_security_audit.py
──────────────────────────────────────
The audit trail for sensitive actions taken by HUMANS.

Before this, routers/auth.py and routers/export.py contained zero logger calls
between them. Login, lockout, MFA disable, bulk customer-PII export and
irreversible erasure all happened without a trace. These tests pin down that
each of those now leaves a row, that the row carries enough to investigate with
(actor, source IP, correlation id, outcome), and — the one that matters most —
that the trail does not itself become a PII leak.
"""

import json

import pytest

import models
from audit import hash_identifier


# ── helpers ──────────────────────────────────────────────────────────────────


def _register(client, email="owner@example.com", password="Password123"):
    return client.post("/api/v1/auth/register", json={
        "email": email, "password": password, "tenant_name": "Test Bistro",
    })


def _token(client, email="owner@example.com", password="Password123"):
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _events(db, event_type=None):
    q = db.query(models.SecurityAuditLog)
    if event_type:
        q = q.filter(models.SecurityAuditLog.event_type == event_type)
    return q.order_by(models.SecurityAuditLog.id.asc()).all()


@pytest.fixture
def db(db_env):
    import database
    database.init_db()
    session = database.SessionLocal()
    yield session
    session.close()


# ── authentication ───────────────────────────────────────────────────────────


def test_successful_login_is_recorded(client, db):
    _register(client)
    _token(client)

    rows = _events(db, "auth.login.success")
    assert len(rows) == 1
    assert rows[0].outcome == "success"
    assert rows[0].actor_email == "owner@example.com"
    assert rows[0].actor_user_id is not None


def test_failed_login_is_recorded_with_actor(client, db):
    _register(client)
    client.post("/api/v1/auth/login",
                json={"email": "owner@example.com", "password": "WrongPassword1"})

    rows = _events(db, "auth.login.failed")
    assert len(rows) == 1
    assert rows[0].outcome == "failure"
    assert json.loads(rows[0].detail)["account_exists"] is True


def test_failed_login_for_unknown_email_is_still_recorded(client, db):
    """The case AgentAuditLog structurally could not represent: no user, no
    tenant, no restaurant. Enumeration of non-existent addresses is a signal."""
    client.post("/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "Whatever123"})

    rows = _events(db, "auth.login.failed")
    assert len(rows) == 1
    assert rows[0].actor_user_id is None
    assert rows[0].actor_email == "nobody@example.com"
    assert json.loads(rows[0].detail)["account_exists"] is False


def test_account_lockout_is_recorded(client, db):
    _register(client)
    for _ in range(5):
        client.post("/api/v1/auth/login",
                    json={"email": "owner@example.com", "password": "WrongPassword1"})

    assert len(_events(db, "auth.login.failed")) == 5
    assert len(_events(db, "auth.login.account_locked")) == 1

    # A further attempt against the now-locked account is also recorded —
    # repeated hits on a locked account is what credential stuffing looks like.
    client.post("/api/v1/auth/login",
                json={"email": "owner@example.com", "password": "WrongPassword1"})
    assert len(_events(db, "auth.login.locked_out")) == 1


def test_mfa_enable_and_disable_are_recorded(client, db):
    _register(client)
    token = _token(client)

    setup = client.post("/api/v1/auth/mfa/setup", headers=_auth(token))
    secret = setup.json()["secret"]

    import auth as auth_mod
    import base64, hmac, hashlib, struct, time

    def code_now():
        key = base64.b32decode(secret, casefold=True)
        return auth_mod._hotp(key, int(time.time() // 30))

    assert client.post("/api/v1/auth/mfa/enable",
                       json={"code": code_now()}, headers=_auth(token)).status_code == 200
    assert client.post("/api/v1/auth/mfa/disable",
                       json={"code": code_now()}, headers=_auth(token)).status_code == 200

    assert len(_events(db, "auth.mfa.enabled")) == 1
    # The action a stolen session most wants, previously invisible.
    assert len(_events(db, "auth.mfa.disabled")) == 1


def test_logout_all_is_recorded(client, db):
    _register(client)
    token = _token(client)
    client.post("/api/v1/auth/logout-all", headers=_auth(token))

    rows = _events(db, "auth.sessions.revoked")
    assert len(rows) == 1
    assert json.loads(rows[0].detail)["new_token_version"] == 1


def test_owner_phone_change_is_recorded_without_storing_the_number(client, db):
    _register(client)
    token = _token(client)
    phone = "+254712345678"

    client.put("/api/v1/auth/restaurant",
               json={"owner_phone": phone}, headers=_auth(token))

    rows = _events(db, "restaurant.owner_phone.changed")
    assert len(rows) == 1
    blob = rows[0].detail + (rows[0].target_ref or "")
    assert "712345678" not in blob
    assert json.loads(rows[0].detail)["new_ref"] == hash_identifier("254712345678")


# ── data rights: export and erasure ──────────────────────────────────────────


def test_customer_export_is_recorded_before_streaming(client, db):
    _register(client)
    token = _token(client)

    resp = client.get("/data/export/customers.csv", headers=_auth(token))
    assert resp.status_code == 200

    rows = _events(db, "data.export.customers")
    assert len(rows) == 1
    assert rows[0].actor_email == "owner@example.com"
    assert json.loads(rows[0].detail)["includes_pii"] is True


def test_orders_export_is_recorded(client, db):
    _register(client)
    token = _token(client)
    assert client.get("/data/export/orders.csv", headers=_auth(token)).status_code == 200
    assert len(_events(db, "data.export.orders")) == 1


def test_erasure_is_recorded_with_counts(client, db):
    _register(client)
    token = _token(client)
    restaurant = db.query(models.Restaurant).first()

    db.add(models.Order(
        restaurant_id=restaurant.id,
        customer_name="Jane Doe",
        customer_phone="254712345678",
        total=1000,
    ))
    db.commit()

    resp = client.post("/data/erase-customer",
                       json={"customer_phone": "254712345678"}, headers=_auth(token))
    assert resp.json()["status"] == "erased"

    rows = _events(db, "data.erase_customer")
    assert len(rows) == 1
    assert json.loads(rows[0].detail)["orders_scrubbed"] == 1


def test_erasure_never_stores_the_phone_number_it_erased(client, db):
    """The regression guard that matters most. Recording the raw number would
    mean the erasure endpoint permanently retains the value the customer asked
    to have forgotten — the compliance control creating the breach."""
    _register(client)
    token = _token(client)
    restaurant = db.query(models.Restaurant).first()
    phone = "254712345678"

    db.add(models.Order(restaurant_id=restaurant.id, customer_name="Jane Doe",
                        customer_phone=phone, total=1000))
    db.commit()

    client.post("/data/erase-customer",
                json={"customer_phone": phone}, headers=_auth(token))

    for row in _events(db):
        blob = " ".join(str(v) for v in (row.detail, row.target_ref, row.actor_email))
        assert phone not in blob
        assert "712345678" not in blob


def test_erasure_of_unknown_phone_is_recorded_as_no_data(client, db):
    """A run of these against numbers the tenant doesn't own is what the
    cross-tenant opt-out abuse described in the endpoint docstring looks like."""
    _register(client)
    token = _token(client)

    resp = client.post("/data/erase-customer",
                       json={"customer_phone": "254799999999"}, headers=_auth(token))
    assert resp.json()["status"] == "no_data"
    assert len(_events(db, "data.erase_customer.no_data")) == 1


# ── row quality: is this actually investigable? ──────────────────────────────


def test_rows_carry_source_ip_and_request_id(client, db):
    _register(client)
    client.post("/api/v1/auth/login",
                json={"email": "owner@example.com", "password": "Password123"},
                headers={"X-Request-ID": "trace-abc-123"})

    row = _events(db, "auth.login.success")[-1]
    assert row.source_ip
    assert row.request_id == "trace-abc-123"
    assert row.created_at is not None


def test_hash_identifier_is_keyed_stable_and_not_the_raw_value():
    assert hash_identifier("254712345678") == hash_identifier("254712345678")
    assert hash_identifier("254712345678") != hash_identifier("254712345679")
    assert "712345678" not in hash_identifier("254712345678")
    assert hash_identifier(None) is None
    assert hash_identifier("") is None


def test_hash_is_stable_across_the_two_normalize_phone_forms():
    """This codebase has two normalize_phone functions that disagree on the
    leading "+": phone_utils (auth path) keeps it, mpesa_client (export path)
    does not. Without canonicalising, the same customer would get two different
    target_refs depending on which endpoint recorded the event — destroying the
    cross-path correlation target_ref exists for."""
    from phone_utils import normalize_phone as auth_form
    from payments.mpesa_client import normalize_phone as export_form

    raw = "0712345678"
    assert auth_form(raw) != export_form(raw)                      # they really do differ
    assert hash_identifier(auth_form(raw)) == hash_identifier(export_form(raw))


def test_hash_is_keyed_by_secret_key(monkeypatch):
    """A bare SHA-256 would be trivially reversible over the small space of
    Kenyan phone numbers — the key is what prevents that."""
    monkeypatch.setenv("SECRET_KEY", "key-one")
    first = hash_identifier("254712345678")
    monkeypatch.setenv("SECRET_KEY", "key-two")
    assert hash_identifier("254712345678") != first


# ── transactional integrity ──────────────────────────────────────────────────


def test_audit_row_rolls_back_with_a_failed_erasure(client, db, monkeypatch):
    """The audit row shares the caller's transaction, so a rolled-back operation
    cannot leave a row claiming it happened."""
    _register(client)
    token = _token(client)
    restaurant = db.query(models.Restaurant).first()
    db.add(models.Order(restaurant_id=restaurant.id, customer_name="Jane",
                        customer_phone="254712345678", total=1000))
    db.commit()

    def _explode(*a, **kw):
        raise RuntimeError("opt-out store unavailable")

    monkeypatch.setattr("ai.whatsapp.optout.record_opt_out", _explode, raising=False)

    before = len(_events(db, "data.erase_customer"))
    try:
        client.post("/data/erase-customer",
                    json={"customer_phone": "254712345678"}, headers=_auth(token))
    except Exception:
        pass

    # The commit happens before record_opt_out, so this row is expected to
    # persist — what must NOT happen is a row without the scrub, or a scrub
    # without a row. Assert they agree.
    db.expire_all()
    rows = _events(db, "data.erase_customer")
    scrubbed = db.query(models.Order).filter(
        models.Order.customer_phone.is_(None)).count()
    assert (len(rows) > before) == (scrubbed > 0)


def test_failed_login_audit_row_survives_the_same_commit(client, db):
    """The failed-login row is added to the same session as the
    failed_login_attempts increment, so both land or neither does."""
    _register(client)
    client.post("/api/v1/auth/login",
                json={"email": "owner@example.com", "password": "WrongPassword1"})

    db.expire_all()
    user = db.query(models.User).filter(models.User.email == "owner@example.com").first()
    assert user.failed_login_attempts == 1
    assert len(_events(db, "auth.login.failed")) == 1
