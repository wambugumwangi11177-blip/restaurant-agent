"""
backend/ai/cache.py
────────────────────
Process-local TTL cache for the heaviest analytics functions
(ops_manager.get_operations_dashboard, revenue_forecaster.get_revenue_forecast).

Modeled on ai/reasoning/narrator.py's bounded-FIFO `_cache` idiom, but with a
TTL check instead of narrator's content-hash key: narrator can key by a hash
of its payload because the payload *is* the input, while these functions take
(db, restaurant_id) — the input is the database, so freshness has to come
from a clock, not a hash of the arguments.

No new dependency: requirements.txt has no cachetools/redis, and the
single-gunicorn-worker constraint documented in rate_limit.py is exactly why
an in-process dict is correct here (same reasoning as why the in-memory rate
limiter works today).
"""

import time

_store: dict[str, tuple[float, dict]] = {}
_MAX_ENTRIES = 256


def cached(key: str, ttl_seconds: int, compute):
    """Return compute()'s cached result if it's younger than ttl_seconds,
    otherwise call compute(), store, and return it.

    Returns a shallow copy on a hit, never the stored object itself — callers
    downstream (e.g. routers/analytics.py's _with_freshness, which pops/sets
    top-level keys on whatever dict it's handed) must not be able to mutate
    the cached entry. Same reasoning as narrator._cache's `{**cached, ...}`
    copy-on-read.
    """
    now = time.monotonic()
    hit = _store.get(key)
    if hit and now - hit[0] < ttl_seconds:
        return dict(hit[1])
    value = compute()
    if len(_store) >= _MAX_ENTRIES:
        _store.pop(next(iter(_store)))  # crude FIFO eviction, matches narrator's simplicity
    _store[key] = (now, value)
    return dict(value)


def clear() -> None:
    """Test-only: drop all cached entries. Mirrors narrator._cache.clear()."""
    _store.clear()
