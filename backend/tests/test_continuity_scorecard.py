"""Founder-continuity scorecard: deterministic health scoring + SUPERADMIN gate."""
from datetime import timedelta

import auth
import models
from ai.continuity.scorecard import platform_scorecard, restaurant_health
from time_utils import utcnow


def _restaurant(db, suffix):
    t = models.Tenant(name=f"T{suffix}")
    db.add(t); db.commit()
    r = models.Restaurant(tenant_id=t.id, name=f"R{suffix}", address="x")
    db.add(r); db.commit()
    return r


def _orders(db, r, n, days_ago):
    for _ in range(n):
        db.add(models.Order(restaurant_id=r.id, total=1000,
                            created_at=utcnow() - timedelta(days=days_ago)))
    db.commit()


def test_active_restaurant_is_green(db_session):
    r = _restaurant(db_session, "g")
    _orders(db_session, r, 12, 1)
    h = restaurant_health(db_session, r)
    assert h["score"] == 100 and h["status"] == "green" and h["reasons"] == []


def test_silent_restaurant_with_collapse_is_red(db_session):
    r = _restaurant(db_session, "r")
    _orders(db_session, r, 12, 10)  # prior week only, nothing since
    h = restaurant_health(db_session, r)
    assert h["status"] == "red"
    assert any("no orders for" in x for x in h["reasons"])


def test_no_orders_ever_is_flagged(db_session):
    r = _restaurant(db_session, "n")
    h = restaurant_health(db_session, r)
    assert h["score"] == 60 and "no orders recorded" in h["reasons"]


def test_red_share_triggers_human_call(db_session):
    good = _restaurant(db_session, "a"); _orders(db_session, good, 5, 1)
    bad = _restaurant(db_session, "b"); _orders(db_session, bad, 12, 10)
    card = platform_scorecard(db_session)
    assert card["summary"]["red"] == 1 and card["summary"]["needs_human_call"] is True
    assert card["restaurants"][0]["name"] == "Rb"  # worst first


def _token(db, role, suffix):
    t = models.Tenant(name=f"T{suffix}"); db.add(t); db.commit()
    u = models.User(tenant_id=t.id, email=f"{suffix}@e.com",
                    hashed_password=auth.get_password_hash("x"), role=role, token_version=0)
    db.add(u); db.add(models.Restaurant(tenant_id=t.id, name=suffix, address="x")); db.commit()
    return auth.create_access_token({"sub": u.email, "ver": 0})


def test_scorecard_endpoint_is_superadmin_only(client, db_session):
    admin = _token(db_session, models.Role.ADMIN, "own")
    sup = _token(db_session, models.Role.SUPERADMIN, "sup")
    assert client.get("/continuity/scorecard", headers={"Authorization": f"Bearer {admin}"}).status_code == 403
    r = client.get("/continuity/scorecard", headers={"Authorization": f"Bearer {sup}"})
    assert r.status_code == 200 and r.json()["summary"]["total"] >= 1
