"""Tests for retained historical scenario code, which is not mounted in main.app."""
import pytest

@pytest.fixture
def legacy_client(db_env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import database
    from routers import demo
    from rate_limit import limiter
    database.init_db()
    app=FastAPI()
    app.state.limiter=limiter
    app.include_router(demo.router,prefix="/api/v1")
    return TestClient(app)
