"""
backend/middleware/rate_limit_enhanced.py
───────────────────────────────────────────
Enhanced rate limiting configuration.
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
import logging

logger = logging.getLogger("middleware.rate_limit")

# Different limits for different endpoint types
def get_rate_limit_key(request: Request):
    """Generate a rate limit key based on endpoint and IP"""
    # You could make this more sophisticated based on user role, endpoint sensitivity, etc.
    return get_remote_address(request)

# Create limiter with default limits
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=["100 per hour"],  # Default limit
    strategy="fixed-window",  # or "moving-window"
)

# Custom handler that logs rate limit events
async def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    logger.warning(
        f"Rate limit exceeded: {request.method} {request.url.path} "
        f"from {request.client.host if request.client else 'unknown'} "
        f"- Limit: {exc.detail}"
    )
    # You could return a custom response format here
    return await _rate_limit_exceeded_handler(request, exc)