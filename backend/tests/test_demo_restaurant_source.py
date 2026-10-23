"""Demo Restaurant records its data directly: it never waits on MacSoft.

Vibanda Village keeps its owner views empty until a MacSoft delivery has passed
a clean reconcile. Demo Restaurant is the same owner experience for a restaurant
whose system of record is this app, so its source is reported as "direct" and
its own records are trusted as recorded.
"""
import secrets

import models
from routers.overview import records_directly, source_is_trusted
from tests.test_overview_scope import scoped_owner  # noqa: F401


def test_source_trust_rules():
    assert source_is_trusted({"state": "direct", "reconciled": True})
    assert source_is_trusted({"state": "receiving", "reconciled": True})
    assert not source_is_trusted({"state": "receiving", "reconciled": False})
    assert not source_is_trusted({"state": "awaiting_first_delivery", "reconciled": False})
    assert not source_is_trusted({"state": "unavailable", "reconciled": False})


def test_only_the_demo_tenant_records_directly(db_session):
    demo = models.Tenant(name="Demo Restaurant")
    vibanda = models.Tenant(name="Vibanda Village")
    db_session.add_all([demo, vibanda])
    db_session.commit()
    assert records_directly(db_session, demo.id)
    assert not records_directly(db_session, vibanda.id)
    assert not records_directly(db_session, None)


def test_demo_overview_is_live_without_any_macsoft_delivery(client):
    # No mirror tables, no MacSoft source row, no data: a fresh signup.
    resp = client.post("/api/v1/auth/register", json={
        "email": f"demo{secrets.token_hex(4)}@example.com",
        "password": "CorrectHorseBattery1!", "tenant_name": "Demo Restaurant",
    })
    assert resp.status_code == 201, resp.text
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

    body = client.get("/api/v1/overview/today", headers=headers).json()
    provenance = body["data_provenance"]
    assert provenance["source_connection"]["state"] == "direct"
    assert provenance["integration_verified"] is True
    assert "Recorded directly in this system" in provenance["notice"]
    assert body["source_status"]["integration"]["state"] == "direct"
    assert body["restaurant_name"] == "Demo Restaurant"
    assert body["revenue"]["orders"] == 0


def test_startup_hook_provisions_demo_once_and_never_resets_the_password(client, db_session, monkeypatch):
    import auth
    import tenant_provisioning

    monkeypatch.delenv("DEMO_RESTAURANT_OWNER_EMAIL", raising=False)
    tenant_provisioning.provision_demo_from_env()
    assert db_session.query(models.Tenant).filter_by(name="Demo Restaurant").count() == 0

    monkeypatch.setenv("DEMO_RESTAURANT_OWNER_EMAIL", "owner@demo-restaurant.example")
    monkeypatch.setenv("DEMO_RESTAURANT_OWNER_PASSWORD", "FirstPassword123")
    tenant_provisioning.provision_demo_from_env()
    monkeypatch.setenv("DEMO_RESTAURANT_OWNER_PASSWORD", "SecondPassword456")
    tenant_provisioning.provision_demo_from_env()

    db_session.expire_all()
    assert db_session.query(models.Tenant).filter_by(name="Demo Restaurant").count() == 1
    owner = db_session.query(models.User).filter_by(email="owner@demo-restaurant.example").one()
    assert owner.role == models.Role.ADMIN and owner.staff_role == models.StaffRole.OWNER
    assert auth.verify_password("FirstPassword123", owner.hashed_password)

    login = client.post("/api/v1/auth/login/restaurant",
                        json={"restaurant_name": "Demo Restaurant", "password": "FirstPassword123"})
    assert login.status_code == 200, login.text
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}).json()
    assert me["tenant_name"] == "Demo Restaurant" and me["restaurant_name"] == "Demo Restaurant"


def test_demo_staff_logins_use_env_passwords_and_startup_does_not_reset_them(client, db_session, monkeypatch):
    import auth
    import tenant_provisioning

    monkeypatch.setenv("DEMO_RESTAURANT_OWNER_EMAIL", "owner@demo-restaurant.example")
    monkeypatch.setenv("DEMO_RESTAURANT_OWNER_PASSWORD", "OwnerPass123")
    staff = [
        ("DEMO_RESTAURANT_MANAGER_PASSWORD", "manager@demo-restaurant.example", "ManagerPass123", models.StaffRole.MANAGER),
        ("DEMO_RESTAURANT_STOREKEEPER_PASSWORD", "store@demo-restaurant.example", "StorePass123", models.StaffRole.STOCKKEEPER),
        ("DEMO_RESTAURANT_KITCHEN_PASSWORD", "kitchen@demo-restaurant.example", "KitchenPass123", models.StaffRole.KITCHEN),
        ("DEMO_RESTAURANT_ACCOUNTANT_PASSWORD", "accountant@demo-restaurant.example", "Account123", models.StaffRole.CONTROLLER),
    ]
    for env_name, _email, password, _role in staff:
        monkeypatch.setenv(env_name, password)
    tenant_provisioning.provision_demo_from_env()
    db_session.expire_all()
    for _env_name, email, password, role in staff:
        user = db_session.query(models.User).filter_by(email=email).one()
        assert user.staff_role == role and user.role == models.Role.STAFF
        assert auth.verify_password(password, user.hashed_password)
        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
    monkeypatch.setenv("DEMO_RESTAURANT_MANAGER_PASSWORD", "ChangedPass123")
    tenant_provisioning.provision_demo_from_env()
    db_session.expire_all()
    manager = db_session.query(models.User).filter_by(email="manager@demo-restaurant.example").one()
    assert auth.verify_password("ManagerPass123", manager.hashed_password)
    tenant = db_session.query(models.Tenant).filter_by(name="Demo Restaurant").one()
    restaurant = db_session.query(models.Restaurant).filter_by(tenant_id=tenant.id).one()
    tenant_provisioning.upsert_demo_staff(db_session, tenant, restaurant.id, reset_password=True)
    db_session.commit()
    db_session.refresh(manager)
    assert auth.verify_password("ChangedPass123", manager.hashed_password)


def test_demo_owner_os_analyses_recorded_data_without_reconciliation(client, db_session, scoped_owner, monkeypatch):
    from ai import llm_client

    owner, headers = scoped_owner
    db_session.query(models.Tenant).filter_by(id=owner.tenant_id).update({"name": "Demo Restaurant"})
    db_session.commit()
    monkeypatch.setattr(llm_client, "is_available", lambda: False)

    response = client.post("/api/v1/ai/chat", headers=headers, json={
        "question": "What will run out soon?", "answer_mode": "analysis", "topic": "stock",
    })
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["answer_type"] == "restaurant_analysis"
    assert answer["data_availability"] == "available"
    assert "reconciliation" not in (answer["answer_text"] or "").lower()
