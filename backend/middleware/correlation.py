"""
backend/middleware/correlation.py
───────────────────────────────────
Assigns a correlation id to every request and threads it through logging.

Reads an inbound `X-Request-ID` if a caller/proxy supplied one (so a chain of
services can share it), otherwise mints a short one. Stores it in the
`request_id` contextvar that logging_config stamps onto every log record, and
echoes it back in the `X-Request-ID` response header so a client/support ticket
can quote the exact id to grep for.

The id is ALSO stashed on `request.state.request_id`, which is not redundant.
The contextvar is reset in the `finally` below as the response (or an exception)
propagates out of this middleware, but FastAPI's handler for unhandled
exceptions runs inside Starlette's ServerErrorMiddleware — which sits OUTSIDE
all user middleware, i.e. after this reset has already happened. A handler
reading the contextvar there would always see the default "-". `request.state`
survives that unwinding, so it is what main.py's 500 handler reads to put the
correlation id in the error body.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from logging_config import request_id_var


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id")
        request_id = incoming.strip() if incoming and incoming.strip() else uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)
