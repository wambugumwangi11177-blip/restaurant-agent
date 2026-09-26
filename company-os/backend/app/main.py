"""
app/main.py
───────────
Application factory. Run with:
  uvicorn app.main:app --reload            (development)
  gunicorn app.main:app -k uvicorn.workers.UvicornWorker   (production)
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import agents, approvals, auth, governance, memory, records, webhooks
from app.config import check_startup, get_settings
from app.kernel.agents.builtin_agents import register_builtin_agents
from app.kernel.agents.builtin_tools import register_builtin_tools
from app.kernel.notifications import register_subscribers
from app.logging_config import RequestIdMiddleware, setup_logging

logger = logging.getLogger("app")

MAX_BODY_BYTES = 5 * 1024 * 1024
_bootstrapped = False


def bootstrap() -> None:
    """Register kernel tools, agents and event subscribers exactly once per process.
    Departments add their own `register()` call here as they are built."""
    global _bootstrapped
    if _bootstrapped:
        return
    register_builtin_tools()
    register_builtin_agents()
    register_subscribers()
    _bootstrapped = True


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()
    for warning in check_startup(settings):
        logger.warning(warning)
    bootstrap()

    app = FastAPI(
        title="Company OS",
        version=governance.VERSION,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        return await call_next(request)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )

    app.include_router(governance.public_router)
    for module in (auth, records, memory, agents, approvals, governance, webhooks):
        app.include_router(module.router, prefix="/api/v1")
    return app


app = create_app()
