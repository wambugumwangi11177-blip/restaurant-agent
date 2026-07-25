"""
Multi-restaurant switcher — audit remediation, Tier 5 item 11 / tech-debt D4.

Every router resolves "the" restaurant via routers/deps.py's
get_or_create_restaurant/get_restaurant_or_none, which always returned a
tenant's FIRST restaurant with no way for a chain owner to pick a different
one. These tests prove: an unselected user still defaults to the first
restaurant (backward compat — the overwhelming single-restaurant case is
unaffected), GET/POST /restaurants let an Owner list and switch, the switch
actually re-scopes subsequent requests, and a tenant can't select or be
shown another tenant's restaurant.
"""

import auth
import models
from routers.deps import get_or_create_restaurant, get_restaurant_or_none, list_restaurants_for_tenant


def _admin_with_two_restaurants(db_session, suffix="mr"):
    tenant = models.Tenant(name=f"MultiRestaurantTenant{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"owner{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN,
        token_version=0,
    )
    db_session.add(user)
    db_session.commit()
    r1 = models.Restaurant(tenant_id=tenant.id, name="Downtown Branch", address="A")
    r2 = models.Restaurant(tenant_id=tenant.id, name="Uptown Branch", address="B")
    db_session.add_all([r1, r2])
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return user, r1, r2, token


# ── deps.py unit-level behavior ────────────────────────────────────────────

def test_unselected_user_defaults_to_first_restaurant_by_id(db_session):
    user, r1, r2, _ = _admin_with_two_restaurants(db_session, "default")
    assert user.active_restaurant_id is None

    resolved = get_or_create_restaurant(db_session, user)

    assert resolved.id == r1.id  # first by id — unchanged default behavior


def test_selecting_a_restaurant_changes_what_resolves(db_session):
    user, r1, r2, _ = _admin_with_two_restaurants(db_session, "select")

    user.active_restaurant_id = r2.id
    db_session.commit()

    resolved = get_restaurant_or_none(db_session, user)

    assert resolved.id == r2.id


def test_active_restaurant_from_another_tenant_is_ignored(db_session):
    user, r1, r2, _ = _admin_with_two_restaurants(db_session, "crosstenant")
    other_tenant = models.Tenant(name="Other Tenant")
    db_session.add(other_tenant)
    db_session.commit()
    other_restaurant = models.Restaurant(tenant_id=other_tenant.id, name="Not Yours")
    db_session.add(other_restaurant)
    db_session.commit()

    user.active_restaurant_id = other_restaurant.id
    db_session.commit()

    # Falls back to this user's own tenant's first restaurant — never leaks
    # into another tenant's data just because the FK column was set to it.
    resolved = get_restaurant_or_none(db_session, user)
    assert resolved.id == r1.id


def test_list_restaurants_for_tenant_returns_only_this_tenants_restaurants(db_session):
    user, r1, r2, _ = _admin_with_two_restaurants(db_session, "list")
    other_tenant = models.Tenant(name="Other Tenant 2")
    db_session.add(other_tenant)
    db_session.commit()
    db_session.add(models.Restaurant(tenant_id=other_tenant.id, name="Not Yours 2"))
    db_session.commit()

    names = {r.name for r in list_restaurants_for_tenant(db_session, user)}
    assert names == {"Downtown Branch", "Uptown Branch"}


def test_single_restaurant_tenant_behavior_is_completely_unchanged(db_session):
    """The overwhelming majority case: one restaurant, never touches
    active_restaurant_id at all."""
    tenant = models.Tenant(name="SingleRestaurantTenant")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(tenant_id=tenant.id, email="single@e.com", hashed_password="x")
    db_session.add(user)
    db_session.commit()

    resolved = get_or_create_restaurant(db_session, user)  # auto-creates, as before

    assert resolved.tenant_id == tenant.id
    assert db_session.query(models.Restaurant).filter(models.Restaurant.tenant_id == tenant.id).count() == 1


# ── HTTP endpoints ──────────────────────────────────────────────────────────

def test_list_restaurants_endpoint_marks_the_active_one(client, db_session):
    user, r1, r2, token = _admin_with_two_restaurants(db_session, "http_list")
    resp = client.get("/restaurants/", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    body = resp.json()
    assert {r["name"] for r in body} == {"Downtown Branch", "Uptown Branch"}
    active = [r for r in body if r["is_active"]]
    assert len(active) == 1
    assert active[0]["id"] == r1.id  # defaults to first, matches deps.py behavior


def test_select_restaurant_endpoint_switches_active_and_persists(client, db_session):
    user, r1, r2, token = _admin_with_two_restaurants(db_session, "http_select")
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/restaurants/select", json={"restaurant_id": r2.id}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == r2.id
    assert resp.json()["is_active"] is True

    # Persisted — a later, unrelated request sees the switch too.
    follow_up = client.get("/restaurants/", headers=headers)
    active = [r for r in follow_up.json() if r["is_active"]]
    assert active[0]["id"] == r2.id


def test_select_restaurant_rejects_another_tenants_restaurant(client, db_session):
    user, r1, r2, token = _admin_with_two_restaurants(db_session, "http_reject")
    other_tenant = models.Tenant(name="Other Tenant 3")
    db_session.add(other_tenant)
    db_session.commit()
    other_restaurant = models.Restaurant(tenant_id=other_tenant.id, name="Not Yours 3")
    db_session.add(other_restaurant)
    db_session.commit()

    resp = client.post(
        "/restaurants/select",
        json={"restaurant_id": other_restaurant.id},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 404


def test_non_admin_staff_cannot_switch_restaurants(client, db_session):
    tenant = models.Tenant(name="StaffAccessTenant")
    db_session.add(tenant)
    db_session.commit()
    staff_user = models.User(
        tenant_id=tenant.id, email="waiter@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF, staff_role=models.StaffRole.WAITER, token_version=0,
    )
    db_session.add(staff_user)
    db_session.commit()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Only Branch")
    db_session.add(restaurant)
    db_session.commit()
    token = auth.create_access_token({"sub": staff_user.email, "ver": 0})

    resp = client.get("/restaurants/", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 403
