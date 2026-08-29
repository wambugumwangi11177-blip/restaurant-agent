"""
backend/middleware/correlation.py
───────────────────────────────────
Assigns a correlation id to every request and threads it through logging.

Reads an inbound `X-Request-ID` if a caller/proxy supplied one (so a chain of
services can share it), otherwise mints a short one. Stores it in the
`request_id` contextvar that logging_config stamps onto every log record, and
echoes it back in the `X-Request-ID` response header so a client/support ticket
can quote the exact id to grep for.
"""

import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from logging_config import request_id_var

# Allow only safe characters to prevent header injection / log injection.
_SAFE_REQUEST_ID_RE = re.compile(r'^[A-Za-z0-9_\-]{1,64}$')


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id")
        if incoming:
            candidate = incoming.strip()
            # Accept the caller-supplied id only if it matches the safe pattern;
            # otherwise mint a fresh one to avoid header/log injection.
            request_id = candidate if _SAFE_REQUEST_ID_RE.match(candidate) else uuid.uuid4().hex[:16]
        else:
            request_id = uuid.uuid4().hex[:16]

        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)