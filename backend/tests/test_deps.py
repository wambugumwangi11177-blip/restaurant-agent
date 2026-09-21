"""
Shared routers/deps.py — extracted 2026-07-07 to eliminate 8 duplicated/
inconsistent restaurant-lookup implementations across 7 router files (DRY +
consistency fix, see directives/013_production_readiness_roadmap.md).
"""

import models
from routers.deps import get_or_create_restaurant, get_restaurant_or_none


def test_owner_notifications_include_admin_without_staff_role_and_stay_tenant_scoped(db_session):
    from routers.deps import get_staff_users_for_restaurant

    db = db_session
    tenant = models.Tenant(name="In-app owner")
    other = models.Tenant(name="Other owner")
    db.add_all([tenant, other])
    db.flush()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Owner restaurant")
    owner = models.User(tenant_id=tenant.id, email="inapp-owner@example.com",
                        hashed_password="unused", role=models.Role.ADMIN,
                        staff_role=None, is_active=True)
    foreign = models.User(tenant_id=other.id, email="foreign-owner@example.com",
                          hashed_password="unused", role=models.Role.ADMIN, is_active=True)
    inactive = models.User(tenant_id=tenant.id, email="inactive-owner@example.com",
                           hashed_password="unused", role=models.Role.ADMIN, is_active=False)
    db.add_all([restaurant, owner, foreign, inactive])
    db.commit()
    assert [user.id for user in get_staff_users_for_restaurant(
        db, restaurant, [models.StaffRole.OWNER])] == [owner.id]
    assert get_staff_users_for_restaurant(db, restaurant, [models.StaffRole.KITCHEN]) == []
    from ai.whatsapp.brain import send_to_owner
    send_to_owner(db, restaurant, "Recorded stock needs review", "stock_review")
    notification = db.query(models.Notification).filter_by(user_id=owner.id).one()
    assert notification.body == "Recorded stock needs review"
    assert notification.event_type == "stock_review"
    assert db.query(models.Notification).count() == 1


def _make_tenant_and_user(db_session, name="Test Tenant"):
    tenant = models.Tenant(name=name)
    db_session.add(tenant)
    db_session.commit()
    user = models.User(tenant_id=tenant.id, email=f"{name}@example.com", hashed_password="x")
    db_session.add(user)
    db_session.commit()
    return tenant, user


def test_get_or_create_restaurant_creates_when_missing(db_session):
    tenant, user = _make_tenant_and_user(db_session)

    assert db_session.query(models.Restaurant).filter(models.Restaurant.tenant_id == tenant.id).first() is None

    restaurant = get_or_create_restaurant(db_session, user)

    assert restaurant is not None
    assert restaurant.tenant_id == tenant.id
    assert restaurant.name == f"{tenant.name}'s Restaurant"
    # Persisted, not just returned in-memory
    assert db_session.query(models.Restaurant).filter(models.Restaurant.tenant_id == tenant.id).count() == 1


def test_get_or_create_restaurant_returns_existing_without_duplicating(db_session):
    tenant, user = _make_tenant_and_user(db_session)
    existing = models.Restaurant(tenant_id=tenant.id, name="Already Here", address="x")
    db_session.add(existing)
    db_session.commit()

    restaurant = get_or_create_restaurant(db_session, user)

    assert restaurant.id == existing.id
    assert restaurant.name == "Already Here"
    assert db_session.query(models.Restaurant).filter(models.Restaurant.tenant_id == tenant.id).count() == 1


def test_get_restaurant_or_none_does_not_create(db_session):
    tenant, user = _make_tenant_and_user(db_session)

    result = get_restaurant_or_none(db_session, user)

    assert result is None
    # Confirms no side effect — a GET-style lookup must never write data
    assert db_session.query(models.Restaurant).filter(models.Restaurant.tenant_id == tenant.id).count() == 0


def test_get_restaurant_or_none_returns_existing(db_session):
    tenant, user = _make_tenant_and_user(db_session)
    existing = models.Restaurant(tenant_id=tenant.id, name="Found Me", address="x")
    db_session.add(existing)
    db_session.commit()

    result = get_restaurant_or_none(db_session, user)

    assert result is not None
    assert result.id == existing.id
