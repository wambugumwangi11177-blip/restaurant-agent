"""
backend/rate_limit.py
──────────────────────
Shared slowapi Limiter instance. Extracted from main.py 2026-07-07: the
limiter was created and attached to app.state, but no router could import it
without a circular import (main.py imports the routers), so it was never
actually applied to any endpoint — rate limiting was fully configured and
fully inert. Routers import `limiter` from here instead.

Gracefully degrades to a no-op if slowapi isn't installed, matching the
existing optional-dependency pattern elsewhere in this codebase.
"""

import logging

logger = logging.getLogger(__name__)

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    limiter = Limiter(key_func=get_remote_address)
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
