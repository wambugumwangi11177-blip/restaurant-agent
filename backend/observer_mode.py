"""Fail-closed HTTP boundary for the read-only Vibanda deployment."""
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

import feature_flags

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
_OPERATIONAL = (
    "/orders", "/inventory", "/menu", "/reservations", "/tables", "/attendance",
    "/suppliers", "/purchase-orders", "/stock", "/staff", "/cash-reconciliation",
    "/billing", "/events", "/notifications", "/support", "/webhooks", "/ai",
    "/fraud", "/enterprise", "/data", "/overview",
)
_LOCAL_FACT_ENDPOINTS = ("/overview", "/reports", "/ai", "/data")


def observer_mode_enabled() -> bool:
    return feature_flags.is_enabled("observer_mode")


def canonical_path(path: str) -> str:
    path = path.rstrip("/") or "/"
    return path[len("/api/v1"):] if path.startswith("/api/v1/") else path


def is_blocked_request(method: str, path: str) -> bool:
    path = canonical_path(path)
    if path == "/support" or path.startswith("/support/"):
        return True
    if path == "/webhooks" or path.startswith("/webhooks/"):
        return True
    # These endpoints derive their figures from this application's legacy
    # operational tables. In an observer deployment they must not be exposed
    # as if they were Macsoft facts, even as read-only GETs.
    if any(path == p or path.startswith(p + "/") for p in _LOCAL_FACT_ENDPOINTS):
        return True
    return method.upper() in _UNSAFE and any(path == p or path.startswith(p + "/") for p in _OPERATIONAL)


class ObserverModeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if observer_mode_enabled() and is_blocked_request(request.method, request.url.path):
            path = canonical_path(request.url.path)
            return JSONResponse(
                status_code=410 if path == "/support" or path.startswith("/support/") else 403,
                content={"code": "OBSERVER_MODE_WRITE_BLOCKED", "detail": "This read-only deployment does not perform operational actions. Use Macsoft for changes."},
            )
        return await call_next(request)
