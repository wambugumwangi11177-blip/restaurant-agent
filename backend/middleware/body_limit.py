"""
backend/middleware/body_limit.py
──────────────────────────────────
Reject oversized request bodies before they are buffered into memory.

This is a JSON API with no legitimate large-upload endpoint, so an unbounded
request body is purely a memory-exhaustion (DoS) vector: Starlette does not cap
body size by default, and `await request.json()`/`.body()` buffers the whole
payload. We refuse anything over MAX_REQUEST_BODY_BYTES (default 1 MB, tunable)
with 413 before the route ever reads it.

Two layers, because a `Content-Length` header can be omitted (chunked transfer):
  1. Fast path — trust a present Content-Length and reject early.
  2. Fallback — wrap the ASGI receive channel and count bytes as they stream in,
     aborting the moment the running total crosses the limit.
"""

import os
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("uvicorn")

MAX_REQUEST_BODY_BYTES = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(1 * 1024 * 1024)))

_TOO_LARGE = JSONResponse({"detail": "Request body too large"}, status_code=413)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Fast path: honour a declared Content-Length.
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_REQUEST_BODY_BYTES:
                    logger.warning(
                        "[BodyLimit] Rejected %s %s — Content-Length %s exceeds %d",
                        request.method, request.url.path, content_length, MAX_REQUEST_BODY_BYTES,
                    )
                    return _TOO_LARGE
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)

        # 2. Fallback: cap streamed/chunked bodies with no Content-Length by
        #    counting bytes on the receive channel.
        received = 0
        original_receive = request._receive

        async def counting_receive():
            nonlocal received
            message = await original_receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_REQUEST_BODY_BYTES:
                    raise _BodyTooLarge()
            return message

        request._receive = counting_receive
        try:
            return await call_next(request)
        except _BodyTooLarge:
            logger.warning(
                "[BodyLimit] Rejected %s %s — streamed body exceeded %d bytes",
                request.method, request.url.path, MAX_REQUEST_BODY_BYTES,
            )
            return _TOO_LARGE


class _BodyTooLarge(Exception):
    """Internal signal that a streamed body crossed the size limit."""
