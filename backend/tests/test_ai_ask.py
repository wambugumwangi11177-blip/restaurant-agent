"""TDD: GET /api/v1/ai/ask — routes an owner question to the RIGHT ai/ modules."""
import secrets

from tests.factories import seed_owner


def _headers(db_session):
    email = f"ask{secrets.token_hex(4)}@example.com"
    _, _, headers = seed_owner(db_session, email=email, tenant_name="Eleven")
    return headers


def test_ask_returns_card_shape(client, db_session):
    headers = _headers(db_session)
    r = client.get("/api/v1/ai/ask", params={"question": "What will run out soon?"}, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("finding", "why", "impact", "recommendation", "module", "steps"):
        assert key in body, f"missing {key}"


def test_ask_stock_routes_to_inventory(client, db_session):
    headers = _headers(db_session)
    r = client.get("/api/v1/ai/ask", params={"question": "What will run out soon?"}, headers=headers)
    body = r.json()
    assert body["module"] in ("inventory", "reorder")
    assert "food cost" not in body["finding"].lower()


def test_ask_sales_routes_to_revenue(client, db_session):
    headers = _headers(db_session)
    r = client.get("/api/v1/ai/ask", params={"question": "How are my sales today?"}, headers=headers)
    body = r.json()
    assert body["module"] in ("revenue", "sales", "ops")
    assert body["finding"]


def test_ask_bookings_routes_to_reservations(client, db_session):
    headers = _headers(db_session)
    r = client.get("/api/v1/ai/ask", params={"question": "How many bookings do I have today?"}, headers=headers)
    body = r.json()
    assert body["module"] in ("reservations", "bookings")


def test_ask_kitchen_routes_to_kds(client, db_session):
    headers = _headers(db_session)
    r = client.get("/api/v1/ai/ask", params={"question": "What's slowing my kitchen down?"}, headers=headers)
    body = r.json()
    assert body["module"] in ("kitchen", "kds")


def test_ask_staff_routes_to_labor(client, db_session):
    headers = _headers(db_session)
    r = client.get("/api/v1/ai/ask", params={"question": "Am I understaffed today?"}, headers=headers)
    body = r.json()
    assert body["module"] in ("labor", "staff")


def test_ask_profit_routes_to_profit(client, db_session):
    headers = _headers(db_session)
    r = client.get("/api/v1/ai/ask", params={"question": "Why did my profit change?"}, headers=headers)
    body = r.json()
    assert body["module"] in ("profit", "menu", "pricing")


def test_ask_empty_question_422(client, db_session):
    headers = _headers(db_session)
    r = client.get("/api/v1/ai/ask", params={"question": ""}, headers=headers)
    assert r.status_code == 422