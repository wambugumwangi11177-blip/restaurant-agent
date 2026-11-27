"""Data wall: Test Restaurant cannot touch Eleven rows; Jack cannot see owner sales APIs."""
import os

import auth
import models
from tests.factories import seed_owner


def _token(user):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email, 'ver': user.token_version or 0})}"}


def _seed_pair(db_session):
    eleven_o, eleven_r, _ = seed_owner(db_session, email="wall-eleven@e.com", tenant_name="Eleven")
    eleven_t = db_session.query(models.Tenant).filter(models.Tenant.id == eleven_o.tenant_id).one()
    jack = models.User(
        email="wall-jack@eleven.leviii",
        hashed_password=auth.get_password_hash("JackPass123"),
        role=models.Role.STAFF,
        staff_role=models.StaffRole.STOCKKEEPER,
        tenant_id=eleven_t.id,
        is_active=True,
        must_change_password=False,
    )
    db_session.add(jack)
    db_session.flush()
    from time_utils import utcnow

    done = utcnow()
    db_session.add(
        models.StaffSetupProgress(
            user_id=jack.id,
            restaurant_id=eleven_r.id,
            updated_at=done,
            account_completed_at=done,
            questionnaire_completed_at=done,
            recipes_completed_at=done,
        )
    )
    db_session.add(
        models.InventoryItem(
            restaurant_id=eleven_r.id,
            item_name="Eleven-only rice",
            quantity=5,
            unit="kg",
            low_stock_threshold=1,
            cost_per_unit=100,
        )
    )

    test_t = models.Tenant(name="Test Restaurant")
    db_session.add(test_t)
    db_session.flush()
    test_r = models.Restaurant(tenant_id=test_t.id, name="Test Restaurant", address="x")
    db_session.add(test_r)
    db_session.flush()
    test_o = models.User(
        email="wall-test@e.com",
        hashed_password=auth.get_password_hash("TestPass123"),
        role=models.Role.ADMIN,
        staff_role=models.StaffRole.OWNER,
        tenant_id=test_t.id,
        is_active=True,
        must_change_password=False,
        active_restaurant_id=test_r.id,
    )
    db_session.add(test_o)
    db_session.flush()
    db_session.add(
        models.InventoryItem(
            restaurant_id=test_r.id,
            item_name="Test-only beans",
            quantity=3,
            unit="kg",
            low_stock_threshold=1,
            cost_per_unit=50,
        )
    )
    db_session.commit()
    return eleven_o, jack, test_o, eleven_r, test_r


def test_restaurant_owner_cannot_list_platform_restaurants(client, db_session):
    _, _, test_o, _, _ = _seed_pair(db_session)
    r = client.get("/api/v1/admin/platform/restaurants", headers=_token(test_o))
    assert r.status_code == 403


def test_test_user_cannot_read_eleven_stock_via_store_api(client, db_session):
    _, jack, test_o, eleven_r, test_r = _seed_pair(db_session)
    r = client.get("/api/v1/store/items", headers=_token(test_o))
    assert r.status_code == 200
    names = [i["item_name"] for i in r.json().get("items", [])]
    assert "Test-only beans" in names
    assert "Eleven-only rice" not in names

    r2 = client.get("/api/v1/store/items", headers=_token(jack))
    assert r2.status_code == 200
    jack_names = [i["item_name"] for i in r2.json().get("items", [])]
    assert "Eleven-only rice" in jack_names
    assert "Test-only beans" not in jack_names


def test_jack_forbidden_on_overview_and_eleven_summary(client, db_session):
    _, jack, _, _, _ = _seed_pair(db_session)
    assert client.get("/api/v1/overview/today", headers=_token(jack)).status_code == 403
    assert client.get("/api/v1/eleven/summary", headers=_token(jack)).status_code == 403


def test_eleven_owner_forbidden_on_platform_api(client, db_session):
    owner, _, _, _, _ = _seed_pair(db_session)
    assert client.get("/api/v1/admin/platform/restaurants", headers=_token(owner)).status_code == 403


def test_superadmin_lists_restaurants_on_platform_api(client, db_session, monkeypatch):
    owner, _, _, _, test_r = _seed_pair(db_session)
    super_u = models.User(
        email="wall-super@leviii.ai",
        hashed_password=auth.get_password_hash("SuperPass123"),
        role=models.Role.SUPERADMIN,
        staff_role=models.StaffRole.OWNER,
        tenant_id=owner.tenant_id,
        is_active=True,
    )
    db_session.add(super_u)
    db_session.commit()
    listed = client.get("/api/v1/admin/platform/restaurants", headers=_token(super_u))
    assert listed.status_code == 200
    names = {row["tenant_name"] for row in listed.json()}
    assert "Eleven" in names
    assert "Test Restaurant" in names


def test_platform_service_token_lists_restaurants(client, db_session, monkeypatch):
    owner, _, _, _, _ = _seed_pair(db_session)
    monkeypatch.setenv("COMPANY_OS_SERVICE_TOKEN", "test-platform-token")
    monkeypatch.setenv("COMPANY_OS_ACTOR_EMAIL", owner.email)
    r = client.get(
        "/api/v1/admin/platform/restaurants",
        headers={"X-Company-OS-Token": "test-platform-token"},
    )
    assert r.status_code == 200