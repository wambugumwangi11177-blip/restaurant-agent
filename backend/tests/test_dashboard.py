"""
AI dashboard 'recent actions' feed. Regression: it read a nonexistent
`m.direction` column, raising AttributeError that a bare `except: pass`
swallowed — so the panel was silently always empty. This test proves a real
outbound message now shows up, and that internal metering rows don't.
"""

import models
import auth


def _make_user_and_restaurant(db_session):
    tenant = models.Tenant(name="Tenant D")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id, email="owner_d@example.com",
        hashed_password=auth.get_password_hash("x"), role=models.Role.ADMIN,
    )
    restaurant = models.Restaurant(tenant_id=tenant.id, name="Restaurant D", address="x")
    db_session.add_all([user, restaurant])
    db_session.commit()
    return user, restaurant


def test_dashboard_recent_actions_includes_outbound_message(client, db_session):
    user, restaurant = _make_user_and_restaurant(db_session)

    # A real outbound message (has a recipient).
    db_session.add(models.AgentMessage(
        restaurant_id=restaurant.id, recipient="+254712345678",
        message_body="Morning briefing", message_type="morning_briefing", status="sent",
    ))
    # An internal metering-style row (no recipient) — must NOT appear in the feed.
    db_session.add(models.AgentMessage(
        restaurant_id=restaurant.id, recipient="",
        message_body="[meter]", message_type="orchestrator_turn", status="ok",
    ))
    db_session.commit()

    token = auth.create_access_token({"sub": user.email})
    resp = client.get("/ai/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    actions = resp.json()["recent_ai_actions"]
    types = [a["action"] for a in actions]
    assert "Morning briefing sent" in types
    assert "orchestrator_turn" not in types
    assert "morning_briefing" not in types  # raw keys must not leak
