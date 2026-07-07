"""
backend/middleware/security_headers.py
────────────────────────────────────────
Security response headers. Security hardening pass (2026-07-07): none of
these were set anywhere, so every response — including the JSON API
responses served to the frontend — was missing basic browser-enforced
defenses (clickjacking, MIME sniffing, referrer leakage).

No CSP is set here: this is a JSON API, not an HTML-serving app, and CSP is
the frontend's (Vercel/Next.js) responsibility for the pages it renders.
HSTS is safe to set unconditionally — Railway terminates TLS in front of
this app, so every request this middleware sees already arrived over HTTPS.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
