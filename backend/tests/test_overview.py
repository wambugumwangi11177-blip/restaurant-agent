"""TDD: GET /api/v1/overview/today — Restaurant OS home feed (sketch parity)."""
import secrets

from tests.factories import seed_owner


def _headers(db_session):
    email = f"ov{secrets.token_hex(4)}@example.com"
    _, _, headers = seed_owner(db_session, email=email, tenant_name="Eleven")
    return headers


def test_overview_today_shape(client, db_session):
    headers = _headers(db_session)
    r = client.get("/api/v1/overview/today", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    required = {"greeting_date", "restaurant_name", "period", "revenue", "orders",
                "kitchen", "stock", "bookings", "staff", "attention", "pulse", "performance"}
    assert required <= set(body), f"missing: {required - set(body)}"
    assert body["restaurant_name"]


def test_overview_periods(client, db_session):
    headers = _headers(db_session)
    for p in ("1h", "today", "7d", "30d"):
        r = client.get(f"/api/v1/overview/today?period={p}", headers=headers)
        assert r.status_code == 200, r.text
    assert client.get("/api/v1/overview/today?period=year", headers=headers).status_code == 422