"""Jack onboarding steps: account -> questions -> recipes -> stock."""
import uuid

import auth
import models
from tests.factories import seed_owner
from time_utils import utcnow


def _token(user):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email, 'ver': user.token_version or 0})}"}


def test_setup_step_order_and_recipes_locked_until_questions(client, db_session):
    slug = uuid.uuid4().hex[:10]
    email = f"jack-step-{slug}@eleven.leviii"
    owner, restaurant, _ = seed_owner(db_session, tenant_name="Eleven", email=f"owner-step-{slug}@eleven.leviii")
    jack = models.User(
        email=email,
        hashed_password=auth.get_password_hash("TempPass1"),
        role=models.Role.STAFF,
        staff_role=models.StaffRole.STOCKKEEPER,
        tenant_id=owner.tenant_id,
        must_change_password=False,
        is_active=True,
        is_email_verified=True,
        hashed_pin=auth.get_pin_hash("1234"),
    )
    db_session.add(jack)
    db_session.flush()
    db_session.add(
        models.StaffSetupProgress(
            user_id=jack.id,
            restaurant_id=restaurant.id,
            account_completed_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    db_session.commit()
    setup = client.get("/api/v1/staff-setup", headers=_token(jack)).json()
    ids = [s["id"] for s in setup["steps"]]
    assert ids == ["account", "questionnaire", "recipes", "stock"]
    recipes = next(s for s in setup["steps"] if s["id"] == "recipes")
    assert recipes["state"] == "locked"