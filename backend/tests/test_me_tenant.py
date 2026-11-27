"""TDD: /auth/me must expose tenant_name."""
import secrets

from tests.factories import seed_owner


def test_me_includes_tenant_name(client, db_session):
    email = f"tn{secrets.token_hex(4)}@example.com"
    _, _, headers = seed_owner(db_session, email=email, tenant_name="Eleven")
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["tenant_name"] == "Eleven"