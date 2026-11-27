"""Owner Home v11 endpoints."""
from datetime import timedelta

import auth
import models
from tests.factories import seed_owner
from time_utils import utcnow


def _token(user):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email, 'ver': user.token_version or 0})}"}


def test_home_today_and_setup(client, db_session):
    owner, restaurant, _ = seed_owner(db_session, tenant_name="Eleven", email="v11-owner@eleven.leviii")
    r = client.get("/api/v1/eleven/home/today", headers=_token(owner))
    assert r.status_code == 200
    body = r.json()
    assert body["tickets"] == 0
    assert body["has_sales"] is False

    setup = client.get("/api/v1/eleven/home/setup", headers=_token(owner)).json()
    assert len(setup["steps"]) == 3


def test_money_today_and_series(client, db_session):
    owner, restaurant, _ = seed_owner(db_session, tenant_name="Eleven", email="v11-owner@eleven.leviii")
    now = utcnow()
    db_session.add(
        models.Order(
            restaurant_id=restaurant.id,
            total=25000,
            is_paid=True,
            status=models.OrderStatus.SERVED,
            created_at=now - timedelta(days=2),
        )
    )
    db_session.commit()

    today = client.get("/api/v1/eleven/money/today", headers=_token(owner))
    assert today.status_code == 200

    series = client.get("/api/v1/eleven/money/series/sales?days=30", headers=_token(owner))
    assert series.status_code == 200
    data = series.json()
    assert data["has_sales"] is True
    assert data["points"]