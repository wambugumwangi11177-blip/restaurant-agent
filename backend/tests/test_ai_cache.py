"""
ai/cache.py — the in-process TTL cache in front of ops_manager and
revenue_forecaster. Proves: (1) the cache primitive itself hits/expires
correctly, (2) get_operations_dashboard and get_revenue_forecast actually
route through it (a second call within the TTL window doesn't recompute).
"""
import time

from ai import cache as ai_cache


def test_cached_returns_same_value_within_ttl():
    calls = []

    def compute():
        calls.append(1)
        return {"n": len(calls)}

    first = ai_cache.cached("k1", ttl_seconds=60, compute=compute)
    second = ai_cache.cached("k1", ttl_seconds=60, compute=compute)

    assert first == second == {"n": 1}
    assert len(calls) == 1  # compute only ran once


def test_cached_recomputes_after_ttl_expires():
    calls = []

    def compute():
        calls.append(1)
        return len(calls)

    ai_cache.cached("k2", ttl_seconds=0.01, compute=compute)
    time.sleep(0.02)
    second = ai_cache.cached("k2", ttl_seconds=0.01, compute=compute)

    assert second == 2
    assert len(calls) == 2


def test_cached_keys_are_independent():
    ai_cache.cached("a", 60, lambda: "value-a")
    result_b = ai_cache.cached("b", 60, lambda: "value-b")
    assert result_b == "value-b"


def test_ops_dashboard_recompute_avoided_within_ttl(db_session, monkeypatch):
    """get_operations_dashboard must route through the cache, not recompute
    on every call within the TTL window."""
    import models
    from ai import ops_manager

    restaurant = models.Restaurant(id=1, tenant_id=None, name="Kibanda", address="x")
    db_session.add(restaurant)
    db_session.commit()

    calls = []
    real_impl = ops_manager._get_operations_dashboard_impl

    def counting_impl(db, restaurant_id):
        calls.append(1)
        return real_impl(db, restaurant_id)

    monkeypatch.setattr(ops_manager, "_get_operations_dashboard_impl", counting_impl)

    ops_manager.get_operations_dashboard(db_session, 1)
    ops_manager.get_operations_dashboard(db_session, 1)

    assert len(calls) == 1  # second call served from cache


def test_revenue_forecast_recompute_avoided_within_ttl(db_session, monkeypatch):
    import models
    from ai import revenue_forecaster

    restaurant = models.Restaurant(id=1, tenant_id=None, name="Kibanda", address="x")
    db_session.add(restaurant)
    db_session.commit()

    calls = []
    real_impl = revenue_forecaster._get_revenue_forecast_impl

    def counting_impl(db, restaurant_id):
        calls.append(1)
        return real_impl(db, restaurant_id)

    monkeypatch.setattr(revenue_forecaster, "_get_revenue_forecast_impl", counting_impl)

    revenue_forecaster.get_revenue_forecast(db_session, 1)
    revenue_forecaster.get_revenue_forecast(db_session, 1)

    assert len(calls) == 1
