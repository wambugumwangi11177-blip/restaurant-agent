"""TDD: GET /api/v1/overview/today — Restaurant OS home feed (sketch parity)."""
from fastapi.testclient import TestClient


def _register(client):
    import secrets
    email = f"ov{secrets.token_hex(4)}@example.com"
    resp = client.post("/api/v1/auth/register", json={
        "email": email, "password": "CorrectHorseBattery1!", "tenant_name": "Vibanda Village",
    })
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_overview_today_shape(client):
    headers = _register(client)
    r = client.get("/api/v1/overview/today", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    required = {"greeting_date", "restaurant_name", "period", "revenue", "orders",
                "kitchen", "stock", "bookings", "staff", "attention", "pulse", "performance"}
    assert required <= set(body), f"missing: {required - set(body)}"
    assert body["restaurant_name"]


def test_overview_periods(client):
    headers = _register(client)
    for p in ("1h", "today", "7d", "30d"):
        r = client.get(f"/api/v1/overview/today?period={p}", headers=headers)
        assert r.status_code == 200, r.text
    assert client.get("/api/v1/overview/today?period=year", headers=headers).status_code == 422