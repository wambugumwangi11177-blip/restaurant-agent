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


class _NoDb:
    """_llm_narrative rolls the session back if narration raises. Nothing else
    touches the db once narrate_owner is stubbed."""
    def rollback(self):
        pass


def _narrative(monkeypatch, reply, *, revenue, orders):
    """Call _llm_narrative with the metering boundary stubbed.

    narrate_owner (ai/owner_narrative.narrate) locks the tenant row, checks the
    spend cap and meters token usage — a real Tenant/Restaurant/User and a live
    session. These three tests are about the GROUNDING check around it, so they
    stub that boundary and keep the assertions on what _llm_narrative does with
    the text it gets back.
    """
    from routers import reports
    from ai import llm_client
    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(reports, "narrate_owner", reply)
    return reports._llm_narrative("daily", "13 Sep", {"revenue": revenue, "orders": orders},
                                  [], _NoDb(), object(), 1)


def test_report_discards_invented_narrative_figures(monkeypatch):
    assert _narrative(monkeypatch, lambda *a, **k: "Revenue is KSh 999,999.",
                      revenue=500, orders=2) is None


def test_report_keeps_grounded_narrative(monkeypatch):
    assert _narrative(monkeypatch, lambda *a, **k: "Revenue is KSh 500.",
                      revenue=500, orders=2) == "Revenue is KSh 500."


def test_empty_report_does_not_request_speculative_narrative(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Empty records do not prove absent customer activity")

    assert _narrative(monkeypatch, forbidden, revenue=0, orders=0) is None
