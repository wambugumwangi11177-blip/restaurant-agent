"""Dishes summary uses menu engineering matrix on the data stack."""
from datetime import timedelta

import auth
import models
from models import OrderStatus, OrderType, PaymentMethod
from services.eleven_v12_seed import seed_v12_catalog
from tests.factories import seed_owner
from time_utils import utcnow


def _token(user):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email, 'ver': user.token_version or 0})}"}


def _demo_jpeg():
    import base64

    return base64.b64decode(
        "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
        "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwh"
        "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAAR"
        "CAAQABADASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAA"
        "AAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAgP/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMB"
        "AAIRAxEAPwCdABmX/9k="
    )


def test_dishes_summary_returns_sold_dishes(client, db_session):
    owner, restaurant, _ = seed_owner(db_session, tenant_name="Eleven", email="dishes-owner@eleven.leviii")
    seed_v12_catalog(db_session, restaurant, owner, [], _demo_jpeg())
    db_session.commit()

    r = client.get("/api/v1/eleven/money/dishes/summary", headers=_token(owner))
    assert r.status_code == 200
    body = r.json()
    assert body["has_sales"] is True
    assert body["dish_count"] > 0
    assert len(body["quadrant"]) > 0
    assert len(body["bestsellers"]) > 0
    assert body["empty"] is None