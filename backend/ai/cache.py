"""
backend/ai/cache.py
─────────────────────
Tiny in-process TTL cache for the heaviest read-only analytics endpoints
(ops_manager.get_operations_dashboard, revenue_forecaster.get_revenue_forecast).

Same idiom as ai/reasoning/narrator.py's `_cache` dict — process-local, not
shared across workers, not persisted. That's the correct fit here, not a
compromise: the Dockerfile runs a single gunicorn worker (see rate_limit.py's
docstring for why — no Redis is provisioned), so a single process-local cache
is authoritative for the whole app, exactly like the in-memory rate limiter.
If a second worker or Redis is ever added, this needs the same treatment
rate_limit.py already documents for itself.

Not a source of truth — every cached value is a deterministic recomputation
of the same DB query, so a stale hit within the TTL window is a slightly-old
but never-wrong dashboard, not a correctness risk.
"""
import time

_store: dict[str, tuple[float, object]] = {}
_MAX_ENTRIES = 256


def cached(key: str, ttl_seconds: int, compute):
    """
    Return compute()'s result, reused for ttl_seconds if the same key was
    computed recently. `compute` is a zero-arg callable (wrap the real call in
    a lambda/closure at the call site).
    """
    now = time.monotonic()
    hit = _store.get(key)
    if hit is not None and now - hit[0] < ttl_seconds:
        return hit[1]

    value = compute()

    if len(_store) >= _MAX_ENTRIES and key not in _store:
        _store.pop(next(iter(_store)))  # crude FIFO eviction, matches narrator's simplicity

    _store[key] = (now, value)
    return value


def clear() -> None:
    """Test-only: wipe the cache so tests don't leak state across runs."""
    _store.clear()
