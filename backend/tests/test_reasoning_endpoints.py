"""
Integration tests for the reasoning layer over real HTTP.

Drives GET /ai/profit, /ai/menu-engineering, /ai/pricing through the FastAPI app
with the LLM provider STUBBED (no network, no tokens). Proves end to end that:
  • a `narrative` block is attached to each insight endpoint,
  • the grounding guard redacts hallucinated figures over the wire,
  • token usage is metered per tenant,
  • ?narrate=false skips the LLM entirely.

The unit-level grounding behaviour is covered exhaustively in
test_reasoning_grounding.py; these tests lock in the wiring.
"""
from types import SimpleNamespace
from datetime import timedelta

import models
import auth
from time_utils import utcnow


def _seed(db):
    """A user + restaurant with menu items and recent orders, so the
    deterministic modules return real (non-empty, non-error) payloads."""
    tenant = models.Tenant(name="Tenant R")
    db.add(tenant)
    db.commit()

    user = models.User(
        tenant_id=tenant.id, email="owner_r@example.com",
        hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN,
    )
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Restaurant R", address="x")
    db.add_all([user, restaurant])
    db.commit()

    burger = models.MenuItem(restaurant_id=restaurant.id, name="Burger", price=1000,
                             cost_price=300, category="Mains")
    salad = models.MenuItem(restaurant_id=restaurant.id, name="Salad", price=800,
                            cost_price=200, category="Starters")
    db.add_all([burger, salad])
    db.commit()

    base = utcnow()
    for i in range(40):
        when = base - timedelta(days=1 + (i % 20))
        order = models.Order(restaurant_id=restaurant.id, status=models.OrderStatus.SERVED,
                             total=1000, created_at=when)
        db.add(order)
        db.commit()
        item = burger if i % 3 else salad
        db.add(models.OrderItem(order_id=order.id, menu_item_id=item.id,
                                quantity=1, unit_price=item.price))
    db.commit()
    return user, restaurant


def _stub_llm(monkeypatch, reply_text: str):
    """Force the reasoning layer to use a canned LLM reply — no real provider."""
    from ai import llm_client
    from ai.reasoning import narrator
    narrator._cache.clear()  # module-global cache persists across tests in-process

    monkeypatch.setattr(llm_client, "is_available", lambda: True)

    def fake_chat_with_usage(**kwargs):
        return SimpleNamespace(
            text=reply_text, model="stub-model",
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )
    monkeypatch.setattr(llm_client, "chat_with_usage", fake_chat_with_usage)


def _auth(user):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email})}"}


# Qualitative reply with no figures -> must come back verified with nothing redacted.
_QUALITATIVE = (
    '{"headline": "Delivery is your least profitable channel.", '
    '"priorities": ["Your bestseller carries a thin margin."], '
    '"actions": [{"action": "Promote high-margin items", "why": "they lift profit", '
    '"impact": "more profit"}]}'
)


def test_all_three_endpoints_attach_verified_narrative(client, db_session, monkeypatch):
    user, restaurant = _seed(db_session)
    _stub_llm(monkeypatch, _QUALITATIVE)
    headers = _auth(user)

    for endpoint in ("/ai/profit", "/ai/menu-engineering", "/ai/pricing"):
        resp = client.get(endpoint, headers=headers)
        assert resp.status_code == 200, endpoint
        body = resp.json()
        assert "narrative" in body, f"{endpoint} missing narrative"
        n = body["narrative"]
        assert n["headline"] == "Delivery is your least profitable channel."
        assert n["verified"] is True, f"{endpoint} should be verified"
        assert n["ungrounded_numbers"] == []
        assert n["model"] == "stub-model"

    # Token usage was metered for this tenant (one row per narrated endpoint).
    rows = db_session.query(models.TokenUsage).filter(
        models.TokenUsage.restaurant_id == restaurant.id
    ).count()
    assert rows >= 3


def test_grounding_guard_redacts_hallucinated_figure_over_http(client, db_session, monkeypatch):
    user, _ = _seed(db_session)
    # 987654% appears in no payload — the guard must strip and report it.
    _stub_llm(monkeypatch, '{"headline": "Margins are stuck at 987654%.", '
                           '"priorities": [], "actions": []}')

    resp = client.get("/ai/profit", headers=_auth(user))
    assert resp.status_code == 200
    n = resp.json()["narrative"]
    assert n["verified"] is False
    assert "987654%" in n["ungrounded_numbers"]
    assert "987654%" not in n["headline"]
    assert "[unverified]" in n["headline"]


def test_narrate_false_skips_llm(client, db_session, monkeypatch):
    user, _ = _seed(db_session)
    # Stub would raise if called — proves narrate=false never touches the LLM.
    from ai import llm_client
    monkeypatch.setattr(llm_client, "is_available", lambda: True)

    def boom(**kwargs):
        raise AssertionError("LLM must not be called when narrate=false")
    monkeypatch.setattr(llm_client, "chat_with_usage", boom)

    resp = client.get("/ai/profit?narrate=false", headers=_auth(user))
    assert resp.status_code == 200
    assert "narrative" not in resp.json()


def test_missing_provider_still_returns_deterministic_data(client, db_session, monkeypatch):
    user, _ = _seed(db_session)
    from ai import llm_client
    from ai.reasoning import narrator
    narrator._cache.clear()
    monkeypatch.setattr(llm_client, "is_available", lambda: False)  # no provider configured

    resp = client.get("/ai/profit", headers=_auth(user))
    assert resp.status_code == 200
    body = resp.json()
    assert "narrative" not in body          # gracefully omitted
    assert "summary" in body and "error" not in body  # deterministic data intact
