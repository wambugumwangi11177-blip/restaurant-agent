"""TDD: GET /api/v1/reports/{period} — deterministic drafted reports."""
import secrets

from fastapi.testclient import TestClient


def _register(client):
    email = f"rp{secrets.token_hex(4)}@example.com"
    resp = client.post("/api/v1/auth/register", json={
        "email": email, "password": "CorrectHorseBattery1!", "tenant_name": "Vibanda Village",
    })
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def test_reports_daily_shape(client):
    headers = _register(client)
    r = client.get("/api/v1/reports/daily", headers=headers)
    assert r.status_code == 200, r.text
    assert {"period", "range", "revenue", "orders", "top_items", "report_text"} <= set(r.json())
    assert "# Daily report" in r.json()["report_text"]


def test_reports_all_periods(client):
    headers = _register(client)
    for p in ("weekly", "monthly", "yearly"):
        assert client.get(f"/api/v1/reports/{p}", headers=headers).status_code == 200
    assert client.get("/api/v1/reports/hourly", headers=headers).status_code == 422


def test_report_discards_invented_narrative_figures(monkeypatch):
    from routers.reports import _llm_narrative
    from ai import llm_client
    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(llm_client, "chat", lambda *args, **kwargs: "Revenue is KSh 999,999.")
    assert _llm_narrative("daily", "13 Sep", {"revenue": 500, "orders": 2}, []) is None


def test_report_keeps_grounded_narrative(monkeypatch):
    from routers.reports import _llm_narrative
    from ai import llm_client
    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(llm_client, "chat", lambda *args, **kwargs: "Revenue is KSh 500.")
    assert _llm_narrative("daily", "13 Sep", {"revenue": 500, "orders": 2}, []) == "Revenue is KSh 500."
