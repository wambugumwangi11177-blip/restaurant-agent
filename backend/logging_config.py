"""
backend/logging_config.py
──────────────────────────
Structured logging + request correlation.

Previously the app logged plain f-strings (and stray `print()`s) with no
configured formatter, so on Railway the logs were unsearchable free text with no
way to tie the lines of a single request together. This module:

  • emits one JSON object per log line (LOG_FORMAT=json, the default) so Railway/
    any aggregator can filter by field — set LOG_FORMAT=plain for readable local dev;
  • stamps every record with a `request_id` pulled from a contextvar, so all the
    log lines produced while handling one HTTP request share an id (set by
    middleware.correlation.CorrelationIdMiddleware).

The request_id is a *synchronous* correlation key: it threads through
HTTP → AI → DB within one request. It cannot cross into an inbound M-Pesa/Twilio
webhook (a separate request Safaricom/Twilio initiates) — for that async
boundary the business key is `order_id`, which the payment path already logs.
"""

import json
import logging
import os
import sys
from contextvars import ContextVar

# Set per-request by CorrelationIdMiddleware; "-" outside any request (startup,
# scheduler jobs, tests).
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# LogRecord attributes we never want to duplicate into the JSON "extra" bucket.
_STD_ATTRS = set(vars(logging.makeLogRecord({})).keys()) | {"request_id", "message", "asctime", "taskName"}


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Pass through structured extras (logger.info(..., extra={"order_id": 5})).
        for key, value in record.__dict__.items():
            if key not in _STD_ATTRS and not key.startswith("_"):
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Install a single stdout handler on the root logger. Idempotent."""
    log_format = os.getenv("LOG_FORMAT", "json").lower()
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    if log_format == "plain":
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"
        ))
    else:
        handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Let uvicorn's loggers flow through our root handler instead of their own,
    # so access/error lines are structured and carry the request_id too.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
