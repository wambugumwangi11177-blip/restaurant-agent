"""Home returns numbers without waiting on a model, and stays under a second on a busy local set."""
import time

import auth
import models
from owner.home import compose_home
from owner.states import OwnerContext
from routers.deps import get_or_create_restaurant
from time_utils import utcnow


def test_home_skips_the_model_and_finishes_within_a_second(db_session, monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("Home waited on an insight")

    monkeypatch.setattr("ai.insight.attach", explode)
    tenant = models.Tenant(name="Speed")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(tenant_id=tenant.id, email="speed@e.com", hashed_password=auth.get_password_hash("x"),
                       role=models.Role.ADMIN, token_version=0)
    db_session.add(user)
    db_session.commit()
    restaurant = get_or_create_restaurant(db_session, user)
    now = utcnow()
    db_session.add_all([
        models.Order(restaurant_id=restaurant.id, status=models.OrderStatus.SERVED, is_paid=True,
                     payment_method=models.PaymentMethod.CASH, total=1500, created_at=now)
        for _ in range(220)
    ])
    db_session.add_all([
        models.CashDrawerCount(
            restaurant_id=restaurant.id,
            window_start=now.replace(microsecond=0),
            window_end=now.replace(microsecond=0),
            expected_amount_cents=1000 + i,
            counted_amount_cents=1000,
            counted_by_user_id=user.id,
            counted_at=now,
        )
        for i in range(30)
    ])
    db_session.commit()
    ctx = OwnerContext(db_session, user, restaurant)
    compose_home(ctx, "today")
    started = time.perf_counter()
    home = compose_home(ctx, "today")
    elapsed = time.perf_counter() - started
    assert "insight" not in home
    assert home["read"]["text"] is None
    assert home["pulse"]["orders_today"] == 220
    assert set(home["figures"]) >= {"three_way", "short_count", "pareto", "door_cards"}
    assert elapsed < 1.0, f"home took {elapsed:.2f}s"
