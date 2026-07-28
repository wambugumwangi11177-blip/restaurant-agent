"""
TTL cache on the two heaviest analytics functions (ai/cache.py). Verifies:
  - a second call within the TTL window does NOT recompute (proven by a call
    counter on the wrapped function, following test_narrator_golden.py's style
    of stubbing the expensive part rather than asserting on real DB timing),
  - a call after the TTL expires DOES recompute,
  - different restaurant_ids never share a cache entry,
  - the cache never hands back a mutable reference to its own stored value
    (routers/analytics.py's _with_freshness pops/sets keys on whatever dict
    it receives — a shared reference would corrupt the cached entry).
"""

import models
import auth
from ai import cache as ai_cache
from ai import ops_manager, revenue_forecaster


def _make_user_and_restaurant(db_session, suffix):
    tenant = models.Tenant(name=f"Tenant {suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id, email=f"owner_{suffix}@example.com",
        hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN,
    )
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"Restaurant {suffix}", address="x")
    db_session.add_all([user, restaurant])
    db_session.commit()
    return user, restaurant


def test_cached_helper_only_recomputes_after_ttl_expires(monkeypatch):
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return {"n": calls["n"]}

    clock = {"t": 1000.0}
    monkeypatch.setattr(ai_cache.time, "monotonic", lambda: clock["t"])

    first = ai_cache.cached("k", 60, compute)
    assert first == {"n": 1}
    assert calls["n"] == 1

    # Still within TTL — must not recompute.
    clock["t"] += 30
    second = ai_cache.cached("k", 60, compute)
    assert second == {"n": 1}
    assert calls["n"] == 1

    # Past TTL — must recompute.
    clock["t"] += 31
    third = ai_cache.cached("k", 60, compute)
    assert third == {"n": 2}
    assert calls["n"] == 2


def test_cached_helper_does_not_leak_a_mutable_reference():
    def compute():
        return {"a": 1}

    first = ai_cache.cached("mutation-key", 60, compute)
    first["a"] = 999
    first["injected"] = True

    second = ai_cache.cached("mutation-key", 60, compute)
    assert second == {"a": 1}
    assert "injected" not in second


def test_get_operations_dashboard_is_cached_across_calls(db_session, monkeypatch):
    ai_cache.clear()
    user, restaurant = _make_user_and_restaurant(db_session, "ops")

    calls = {"n": 0}
    real = ops_manager._get_operations_dashboard_uncached

    def counting(db, restaurant_id):
        calls["n"] += 1
        return real(db, restaurant_id)

    monkeypatch.setattr(ops_manager, "_get_operations_dashboard_uncached", counting)

    first = ops_manager.get_operations_dashboard(db_session, restaurant.id)
    second = ops_manager.get_operations_dashboard(db_session, restaurant.id)

    assert calls["n"] == 1, "second call within TTL must reuse the cached result"
    assert first["health_score"] == second["health_score"]


def test_get_revenue_forecast_is_cached_per_restaurant(db_session, monkeypatch):
    ai_cache.clear()
    user_a, restaurant_a = _make_user_and_restaurant(db_session, "rev_a")
    user_b, restaurant_b = _make_user_and_restaurant(db_session, "rev_b")

    calls = {"n": 0}
    real = revenue_forecaster._get_revenue_forecast_uncached

    def counting(db, restaurant_id):
        calls["n"] += 1
        return real(db, restaurant_id)

    monkeypatch.setattr(revenue_forecaster, "_get_revenue_forecast_uncached", counting)

    revenue_forecaster.get_revenue_forecast(db_session, restaurant_a.id)
    revenue_forecaster.get_revenue_forecast(db_session, restaurant_a.id)
    assert calls["n"] == 1, "same restaurant, second call must hit the cache"

    revenue_forecaster.get_revenue_forecast(db_session, restaurant_b.id)
    assert calls["n"] == 2, "a different restaurant must never share a cache entry"


def test_dashboard_route_response_is_stable_across_cached_calls(client, db_session):
    """
    Route-level check that _with_freshness's in-place pop/set of top-level
    keys (routers/analytics.py) never corrupts the cached ops_manager entry —
    two requests within the TTL window must both succeed with the same shape.
    """
    ai_cache.clear()
    user, restaurant = _make_user_and_restaurant(db_session, "route")
    token = auth.create_access_token({"sub": user.email})
    headers = {"Authorization": f"Bearer {token}"}

    r1 = client.get("/ai/dashboard", headers=headers)
    r2 = client.get("/ai/dashboard", headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["health_score"] == r2.json()["health_score"]
    assert "freshness" in r1.json()
    assert "freshness" in r2.json()
