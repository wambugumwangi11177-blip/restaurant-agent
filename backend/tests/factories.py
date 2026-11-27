"""Test data factories — no public signup endpoints."""
from __future__ import annotations

import auth
import models


def seed_owner(
    db_session,
    *,
    email: str = "owner@test.example",
    password: str | None = "CorrectHorseBattery1!",
    tenant_name: str = "Test Tenant",
    is_email_verified: bool = True,
) -> tuple[models.User, models.Restaurant, dict[str, str]]:
    tenant = models.Tenant(name=tenant_name)
    db_session.add(tenant)
    db_session.flush()
    user = models.User(
        email=email,
        hashed_password=auth.get_password_hash(password) if password else None,
        role=models.Role.ADMIN,
        staff_role=models.StaffRole.OWNER,
        tenant_id=tenant.id,
        is_email_verified=is_email_verified,
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    restaurant = models.Restaurant(tenant_id=tenant.id, name=tenant_name, address="Nairobi")
    db_session.add(restaurant)
    db_session.flush()
    user.active_restaurant_id = restaurant.id
    db_session.commit()
    db_session.refresh(user)
    token = auth.create_access_token(data={"sub": user.email, "ver": user.token_version or 0})
    return user, restaurant, {"Authorization": f"Bearer {token}"}


def bearer_for(user: models.User) -> dict[str, str]:
    token = auth.create_access_token(data={"sub": user.email, "ver": user.token_version or 0})
    return {"Authorization": f"Bearer {token}"}