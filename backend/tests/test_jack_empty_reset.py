"""Test-stack jack-empty reset and recipe delete."""
import os

import auth
import models
from leviii_test_seed import JACK_EMPTY_EMAIL, reset_jack_empty_journey
from tests.factories import seed_owner


def test_reset_jack_empty_requires_seed_flag(db_session, monkeypatch):
    monkeypatch.delenv("SEED_TEST_DATA", raising=False)
    monkeypatch.setenv("SEED_TEST_DATA", "0")
    try:
        reset_jack_empty_journey(db_session)
        assert False, "expected SeedError"
    except Exception as exc:
        assert "SEED_TEST_DATA" in str(exc)


def test_delete_recipe_line(client, db_session, monkeypatch):
    from tests.test_storekeeper_foundation import _add_staff, _auth, _token, _unlock

    monkeypatch.setenv("SEED_TEST_DATA", "1")
    owner, restaurant, _ = seed_owner(db_session, tenant_name="Eleven", email="owner-del-recipe@eleven.leviii")
    tenant = db_session.query(models.Tenant).filter(models.Tenant.id == owner.tenant_id).one()
    jack = _add_staff(db_session, tenant, restaurant, "jack-del-recipe@eleven.leviii", models.StaffRole.STOCKKEEPER)
    headers = _auth(_token(jack))
    _unlock(client, jack)
    saved = client.post(
        "/api/v1/store/recipes",
        headers=headers,
        json={
            "dish_name": "Soup",
            "ingredient_name": "Salt",
            "quantity": 1,
            "unit": "g",
            "yield_fraction": 1,
        },
    )
    assert saved.status_code == 201
    line_id = saved.json()["dishes"][0]["lines"][0]["id"]
    deleted = client.delete(f"/api/v1/store/recipes/lines/{line_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["dishes"] == []