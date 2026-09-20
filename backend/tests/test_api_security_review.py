"""
backend/tests/test_api_security_review.py
──────────────────────────────────────────
Regression cover for the three findings of the 2026-09-20 API security
review. Each of these closed a hole that the standard checklist did NOT
catch — the endpoints were already authenticated, already tenant-scoped,
already field-whitelisted — so the failure mode for all three is a quiet
revert nobody notices. Hence a test per invariant rather than a comment.

1. PUT /inventory/{item_id} must not be able to change stock on hand.
   Quantity changes leave an audit trail only when they go through
   /receive or /adjust (StockMovement + performed_by_user_id + event).
2. Raising WEB_CONCURRENCY without a shared rate-limit store must fail a
   production boot, not silently multiply every auth rate limit.
3. /docs, /redoc and /openapi.json must not be public in production.
"""

import pytest

import auth
import models
import startup_checks


def _stockkeeper(db_session, suffix="secreview"):
    """A Stockkeeper — inventory's write tier, and the tier the variance
    report exists to oversee. If anyone can bypass the audit trail it is
    most consequentially this one."""
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"u{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF,
        staff_role=models.StaffRole.STOCKKEEPER,
        is_active=True,
        token_version=0,
    )
    db_session.add(user)
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add(restaurant)
    db_session.commit()
    item = models.InventoryItem(
        restaurant_id=restaurant.id,
        item_name="Beef",
        quantity=100.0,
        unit="kg",
        cost_per_unit=500.0,
        low_stock_threshold=10,
    )
    db_session.add(item)
    db_session.commit()
    token = auth.create_access_token({"sub": user.email, "ver": 0})
    return token, user, restaurant, item


# ── 1. Inventory quantity cannot be written without an audit trail ───────────

def test_put_inventory_rejects_quantity(client, db_session):
    """The finding itself: PUT used to accept `quantity` and write it with a
    bare setattr — no StockMovement, no performed_by_user_id, no event. A
    Stockkeeper could zero out stock and the nightly variance check
    (ai/stock_custody.py sums StockMovement OUT) would never see it."""
    token, _user, _restaurant, item = _stockkeeper(db_session, "putqty")

    r = client.put(
        f"/inventory/{item.id}",
        json={"quantity": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422

    # And the stock genuinely did not move.
    db_session.refresh(item)
    assert item.quantity == 100.0


def test_put_inventory_quantity_error_names_the_audited_routes(client, db_session):
    """A bare extra="forbid" 422 says only "not permitted", which reads like
    a typo. The caller needs to be told where the audited path is, or they
    will reach for the next thing that works."""
    token, _user, _restaurant, item = _stockkeeper(db_session, "putqtymsg")

    r = client.put(
        f"/inventory/{item.id}",
        json={"quantity": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = r.text
    assert "/adjust" in body and "/receive" in body


def test_put_inventory_still_updates_non_quantity_fields(client, db_session):
    """The fix must not break the endpoint's actual job — renaming an item,
    fixing a unit cost, moving a low-stock threshold."""
    token, _user, _restaurant, item = _stockkeeper(db_session, "putok")

    r = client.put(
        f"/inventory/{item.id}",
        json={"item_name": "Beef sirloin", "cost_per_unit": 650.0, "low_stock_threshold": 20},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    db_session.refresh(item)
    assert item.item_name == "Beef sirloin"
    assert item.cost_per_unit == 650.0
    assert item.quantity == 100.0


def test_adjust_remains_the_audited_path_for_quantity(client, db_session):
    """The counterpart: the route we redirect callers to must actually write
    the trail, otherwise the fix just moves the blind spot."""
    token, user, _restaurant, item = _stockkeeper(db_session, "adjustok")

    r = client.post(
        f"/inventory/{item.id}/adjust",
        json={"quantity": -12, "reason": "spoilage"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200

    movement = (
        db_session.query(models.StockMovement)
        .filter(models.StockMovement.inventory_item_id == item.id)
        .one()
    )
    assert movement.quantity == 12
    assert movement.performed_by_user_id == user.id


# ── 2. Rate limiting cannot be silently multiplied by scaling out ────────────

def test_multi_worker_without_shared_store_blocks_production_boot(monkeypatch):
    """rate_limit.py documents that >1 worker with an in-memory counter makes
    every limit N times looser — it already shipped that way once. The
    Dockerfile's --workers pin was the fix, but nothing enforced it."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", "t")
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    monkeypatch.delenv("RATE_LIMIT_STORAGE_URI", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    hard, _soft = startup_checks.collect_problems()
    assert any("WEB_CONCURRENCY" in h for h in hard)

    with pytest.raises(RuntimeError):
        startup_checks.enforce_startup_checks()


def test_multi_worker_with_shared_store_is_fine(monkeypatch):
    """Redis is the real fix, and it must actually lift the restriction —
    otherwise the check just becomes something to work around."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", "t")
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    monkeypatch.setenv("RATE_LIMIT_STORAGE_URI", "redis://localhost:6379")

    hard, _soft = startup_checks.collect_problems()
    assert not any("WEB_CONCURRENCY" in h for h in hard)


def test_single_worker_without_shared_store_only_warns(monkeypatch):
    """The current production shape: one worker, no Redis. Correct, but the
    operator should be told the guarantee rests on the worker count."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("MPESA_CALLBACK_TOKEN", "t")
    monkeypatch.setenv("WEB_CONCURRENCY", "1")
    monkeypatch.delenv("RATE_LIMIT_STORAGE_URI", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    hard, soft = startup_checks.collect_problems()
    assert not any("WEB_CONCURRENCY" in h for h in hard)
    assert any("shared rate-limit store" in s for s in soft)


def test_multi_worker_outside_production_only_warns(monkeypatch):
    """Never block local/CI — same posture as every other check in this file."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("MPESA_ENV", raising=False)
    monkeypatch.setenv("SECRET_KEY", "x")
    monkeypatch.setenv("WEB_CONCURRENCY", "4")
    monkeypatch.delenv("RATE_LIMIT_STORAGE_URI", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    hard, soft = startup_checks.collect_problems()
    assert not hard
    assert any("WEB_CONCURRENCY" in s for s in soft)
    startup_checks.enforce_startup_checks()  # must not raise


def test_worker_count_survives_a_junk_value(monkeypatch):
    """A malformed WEB_CONCURRENCY must not crash the boot guard — failing to
    parse it is not a reason to refuse to start."""
    monkeypatch.setenv("WEB_CONCURRENCY", "two")
    assert startup_checks._worker_count() == 1


# ── 3. The OpenAPI schema is not public in production ────────────────────────
#
# These assert startup_checks.docs_enabled() — the policy — plus one check
# that main.py's app is actually wired to it. Deliberately NOT by reloading
# main: that swaps out the module-level `app` object which test_health.py
# (and others) captured at import time, so their dependency_overrides land on
# a stale app and fail for reasons unrelated to what they test. Found the hard
# way while writing this file.

def test_docs_enabled_outside_production(monkeypatch):
    """CI, local and sandbox keep the schema — it is a working tool there,
    and test_versioning_and_sessions.py reads /openapi.json."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("MPESA_ENV", raising=False)
    monkeypatch.delenv("ENABLE_DOCS", raising=False)
    assert startup_checks.docs_enabled() is True


def test_docs_disabled_in_production(monkeypatch):
    """The route map — including the shape of /webhooks/mpesa/{token}, whose
    only authentication IS that token — must not be handed out for free."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ENABLE_DOCS", raising=False)
    assert startup_checks.docs_enabled() is False


def test_mpesa_production_also_counts_as_production(monkeypatch):
    """is_production() is true on MPESA_ENV too — real money moving is exactly
    when the schema should not be public. Guards against the docs check
    drifting onto a narrower definition than the rest of the boot guard."""
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("MPESA_ENV", "production")
    monkeypatch.delenv("ENABLE_DOCS", raising=False)
    assert startup_checks.docs_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes"])
def test_enable_docs_escape_hatch_works_in_production(monkeypatch, value):
    """A deliberate, temporary opt-in for debugging a live deploy — the same
    posture METRICS_TOKEN gives /metrics."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_DOCS", value)
    assert startup_checks.docs_enabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no", "  "])
def test_enable_docs_requires_an_affirmative_value(monkeypatch, value):
    """An empty or falsy ENABLE_DOCS must not re-open the schema — someone
    setting it to "0" to turn it off should get it off."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_DOCS", value)
    assert startup_checks.docs_enabled() is False


def test_app_is_wired_to_the_docs_policy(client):
    """The policy is only worth testing if main.py actually uses it. Under the
    test environment (not production) docs are on, and the app must agree."""
    import main

    assert startup_checks.docs_enabled() is True
    assert main.app.openapi_url == "/openapi.json"
    assert client.get("/openapi.json").status_code == 200
