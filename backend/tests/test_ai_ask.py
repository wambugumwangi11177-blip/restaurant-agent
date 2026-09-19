"""TDD: GET /api/v1/ai/ask — routes an owner question to the RIGHT ai/ modules
and returns a sketch-format answer card (Finding / Why / Impact / Recommendation /
Steps). This is the fix for /ai/strategy ignoring the question entirely."""
import random

from fastapi.testclient import TestClient


def _register(client):
    email = f"ask{random.randint(1000, 9999)}@example.com"
    r = client.post("/api/v1/auth/register", json={
        "email": email, "password": "CorrectHorseBattery1!", "tenant_name": "Vibanda Village"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_ask_returns_card_shape(client):
    headers = _register(client)
    r = client.get("/api/v1/ai/ask", params={"question": "What will run out soon?"}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("finding", "why", "impact", "recommendation", "module", "steps"):
        assert key in body, f"missing {key}"


def test_ask_stock_routes_to_inventory(client):
    headers = _register(client)
    r = client.get("/api/v1/ai/ask", params={"question": "What will run out soon?"}, headers=headers)
    body = r.json()
    # Must route to an inventory/stock module, not menu pricing
    assert body["module"] in ("inventory", "reorder")
    # And the finding must be about stock, not food cost
    assert "food cost" not in body["finding"].lower()


def test_ask_sales_routes_to_revenue(client):
    headers = _register(client)
    r = client.get("/api/v1/ai/ask", params={"question": "How are my sales today?"}, headers=headers)
    body = r.json()
    assert body["module"] in ("revenue", "sales", "ops")
    assert body["finding"]  # non-empty


def test_ask_bookings_routes_to_reservations(client):
    headers = _register(client)
    r = client.get("/api/v1/ai/ask", params={"question": "How many bookings do I have today?"}, headers=headers)
    body = r.json()
    assert body["module"] in ("reservations", "bookings")


def test_ask_kitchen_routes_to_kds(client):
    headers = _register(client)
    r = client.get("/api/v1/ai/ask", params={"question": "What's slowing my kitchen down?"}, headers=headers)
    body = r.json()
    assert body["module"] in ("kitchen", "kds")


def test_ask_staff_routes_to_labor(client):
    headers = _register(client)
    r = client.get("/api/v1/ai/ask", params={"question": "Am I understaffed today?"}, headers=headers)
    body = r.json()
    assert body["module"] in ("labor", "staff")


def test_ask_profit_routes_to_profit(client):
    headers = _register(client)
    r = client.get("/api/v1/ai/ask", params={"question": "Why did my profit change?"}, headers=headers)
    body = r.json()
    assert body["module"] in ("profit", "menu", "pricing")


def test_ask_empty_question_422(client):
    headers = _register(client)
    r = client.get("/api/v1/ai/ask", params={"question": ""}, headers=headers)
    assert r.status_code == 422