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

# The few paths that take a FILE, not JSON, and so may carry more. Keep this list short and each entry bounded: the body is read before
# the caller is authenticated, so every byte allowed here is allowed to anyone. A statement is at most 5 MB (parsers/mpesa_csv.MAX_BYTES)
# plus the multipart form's framing.
LARGER_BODY_PATHS: dict[str, int] = {"/api/v1/owner/mpesa/statement": 6 * 1024 * 1024}


def limit_for(path: str) -> int:
    return max(MAX_REQUEST_BODY_BYTES, LARGER_BODY_PATHS.get(path, 0))

_TOO_LARGE = JSONResponse({"detail": "Request body too large"}, status_code=413)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        limit = limit_for(request.url.path)
        # 1. Fast path: honour a declared Content-Length.
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > limit:
                    logger.warning(
                        "[BodyLimit] Rejected %s %s — Content-Length %s exceeds %d",
                        request.method, request.url.path, content_length, limit,
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
                if received > limit:
                    raise _BodyTooLarge()
            return message

        request._receive = counting_receive
        try:
            return await call_next(request)
        except _BodyTooLarge:
            logger.warning(
                "[BodyLimit] Rejected %s %s — streamed body exceeded %d bytes",
                request.method, request.url.path, limit,
            )
            return _TOO_LARGE


class _BodyTooLarge(Exception):
    """Internal signal that a streamed body crossed the size limit."""
