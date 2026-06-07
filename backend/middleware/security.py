"""
backend/middleware/security.py
──────────────────────────────
Security middleware for enhancing protection.

Includes:
- Security headers (HSTS, CSP, X-Frame-Options, etc.)
- Request size limiting
- Basic input sanitization hints
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.status import HTTP_413_REQUEST_ENTITY_TOO_LARGE
import logging

logger = logging.getLogger("middleware.security")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Security Headers
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy - adjust as needed for your frontend
        # This is a restrictive policy; adjust based on actual resource sources
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers["Content-Security-Policy"] = csp_policy

        # Remove server header (if possible, but Starlette/Uvicorn may not allow easy removal)
        # response.headers["Server"] = ""  # This might not be allowed or effective

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to limit the size of incoming requests to prevent payload attacks.
    """

    def __init__(self, app, max_size: int = 10 * 1024 * 1024):  # Default 10MB
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next):
        # Check Content-Length header
        if request.headers.get("content-length"):
            content_length = int(request.headers["content-length"])
            if content_length > self.max_size:
                logger.warning(
                    f"Request too large: {content_length} bytes from {request.client.host}"
                )
                return Response(
                    content="Request entity too large",
                    status_code=HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )

        # Note: For chunked transfers, we cannot know the size beforehand without reading the body.
        # For simplicity, we rely on the content-length header. If your API does not send
        # content-length, you may need to read the body and check its size, but that is more expensive.
        response: Response = await call_next(request)
        return response