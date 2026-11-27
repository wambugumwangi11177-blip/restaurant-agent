"""GET smoke for role-scoped API routes the Eleven frontend calls."""
from __future__ import annotations

import auth
import models
from tests.test_storekeeper_foundation import _add_staff, _auth, _tenant, _unlock


def _login(client, email, password="TempPass1"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_role_get_routes_not_server_error(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "smoke-owner@eleven.leviii")
    jack = _add_staff(
        db_session, tenant, restaurant, "jack-smoke@eleven.leviii", models.StaffRole.STOCKKEEPER
    )
    amina = _add_staff(
        db_session, tenant, restaurant, "amina-smoke@eleven.leviii", models.StaffRole.CONTROLLER
    )
    owner.active_restaurant_id = restaurant.id
    jack.active_restaurant_id = restaurant.id
    amina.active_restaurant_id = restaurant.id
    db_session.commit()

    specs: list[tuple[str, str, list[str]]] = [
        (
            owner.email,
            "Ownerpass1",
            [
                "/api/v1/store/approvals",
                "/api/v1/eleven/money/pnl",
                "/api/v1/eleven/outcomes/alerts",
                "/api/v1/staff",
            ],
        ),
        (
            jack.email,
            "TempPass1",
            [
                "/api/v1/staff-setup",
                "/api/v1/store/prep",
                "/api/v1/store/items",
                "/api/v1/store/suppliers",
                "/api/v1/store/deliveries",
                "/api/v1/store/handovers",
                "/api/v1/store/close/expected",
            ],
        ),
        (
            amina.email,
            "TempPass1",
            [
                "/api/v1/store/deliveries",
                "/api/v1/store/costs",
            ],
        ),
    ]

    for email, password, paths in specs:
        login = _login(client, email, password)
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        headers = _auth(token)
        if email == jack.email:
            _unlock(client, jack)
            headers = _auth(login.json()["access_token"])
        for path in paths:
            response = client.get(path, headers=headers)
            assert response.status_code < 500, f"{email} {path} -> {response.status_code} {response.text[:200]}"
            assert response.status_code != 404, f"{email} {path} missing"