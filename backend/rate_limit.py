"""
backend/rate_limit.py
──────────────────────
Shared slowapi Limiter instance. Extracted from main.py 2026-07-07: the
limiter was created and attached to app.state, but no router could import it
without a circular import (main.py imports the routers), so it was never
actually applied to any endpoint — rate limiting was fully configured and
fully inert. Routers import `limiter` from here instead.

Second bug found 2026-07-07, after deploying the above fix: rate limiting
still didn't trigger in production even though the exact same code passed
every local test. Root cause was two compounding issues specific to the
Railway deploy, neither reproducible locally:

1. slowapi's default `get_remote_address` reads `request.client.host` — the
   raw TCP peer. Behind Railway's edge proxy, that's the proxy's own
   connection, not the real client; Railway forwards the real client IP via
   the `X-Forwarded-For` header instead. Using the raw peer meant every
   request looked like it came from the same handful of proxy IPs (or, if
   Railway load-balances across edge nodes, from a shifting set of
   non-client IPs) — either way, not a usable per-user key. Fixed with
   `_client_ip` below, which reads the first hop of X-Forwarded-For and
   falls back to the raw peer for local/direct connections (e.g. tests).

2. slowapi's default storage is an in-process Python dict. `Dockerfile` runs
   `gunicorn --workers 2` — two separate OS processes, each with its own
   copy of that dict, so a client's requests round-robin across two
   *independent* counters and it takes ~2x the configured limit to actually
   trip. Not visible with 1 worker locally. No Redis/Memcached is
   provisioned for this project yet, so the correct fix — a shared external
   store — isn't available without adding infra. Interim fix: `Dockerfile`
   now runs a single worker, which makes the in-memory counter authoritative
   again. FastAPI/uvicorn's single worker is async and handles concurrent
   I/O-bound requests fine at this project's traffic level; the tradeoff is
   losing process-level redundancy (one crash drops all capacity until
   Railway restarts it) and some throughput ceiling. If traffic grows enough
   to need >1 worker, the real fix is `Limiter(storage_uri="redis://...")`
   with a provisioned Redis add-on — not more in-memory workers.
"""

import logging

logger = logging.getLogger(__name__)


def _client_ip(request) -> str:
    """
    Real client IP behind Railway's reverse proxy. Railway (like most
    reverse proxies) terminates the client connection itself and forwards
    the original IP via X-Forwarded-For — request.client.host would just be
    Railway's own proxy. Take the first hop (the original client; later hops
    are intermediate proxies) and fall back to the raw peer for direct
    connections (local dev, tests).
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


try:
    from slowapi import Limiter
    limiter = Limiter(key_func=_client_ip)
    SLOWAPI_AVAILABLE = True
except ImportError:
    SLOWAPI_AVAILABLE = False
    logger.warning("[RateLimit] slowapi not installed — rate limiting disabled. Run: pip install slowapi")

    class _NoOpLimiter:
        """Matches slowapi's decorator interface but does nothing."""
        def limit(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator

    limiter = _NoOpLimiter()
