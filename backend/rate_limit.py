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
   `_client_ip` below, which reads the hop the trusted edge proxy appended
   (from the RIGHT of X-Forwarded-For, spoof-resistant — see its docstring)
   and falls back to the raw peer for local/direct connections (e.g. tests).

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
import os

logger = logging.getLogger(__name__)

# Number of trusted reverse proxies in front of this app. On Railway there is a
# single edge proxy, so the default is 1. Override with TRUSTED_PROXY_HOPS if the
# topology changes (e.g. Cloudflare in front of Railway would be 2).
_TRUSTED_PROXY_HOPS = max(int(os.getenv("TRUSTED_PROXY_HOPS", "1")), 1)


def _client_ip(request) -> str:
    """
    Real client IP behind Railway's reverse proxy — resistant to header spoofing.

    X-Forwarded-For is `client, proxy1, proxy2, ...`: each proxy APPENDS the peer
    it received the connection from to the RIGHT. So the value our trusted edge
    proxy appended is the (N-from-right) hop, where N = number of trusted proxies.
    An attacker who sends `X-Forwarded-For: 1.2.3.4` cannot forge that hop —
    Railway's edge appends the attacker's real IP to the right of it — so we read
    from the right, never `split(",")[0]` (the attacker-controlled leftmost value,
    the old bug: it let anyone mint a fresh key per request and defeat every
    per-IP limit — login brute-force, register spam, paid STK-push abuse).

    Falls back to the raw TCP peer for direct connections (local dev, tests).
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            idx = max(len(parts) - _TRUSTED_PROXY_HOPS, 0)
            return parts[idx]
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
