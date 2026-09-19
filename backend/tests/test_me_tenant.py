"""TDD: /auth/me must expose tenant_name (Vibanda dedicated-dashboard routing)."""
import random


def test_me_includes_tenant_name(client):
    email = f"tn{random.randint(1000, 9999)}@example.com"
    r = client.post("/api/v1/auth/register", json={
        "email": email, "password": "CorrectHorseBattery1!", "tenant_name": "Vibanda Village"})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["tenant_name"] == "Vibanda Village"