import auth
from tests.factories import seed_owner


def _tok(user):
    return {"Authorization": f"Bearer {auth.create_access_token({'sub': user.email, 'ver': user.token_version or 0})}"}


def test_v11_money_endpoints_smoke(client, db_session):
    owner, restaurant, _ = seed_owner(db_session, tenant_name="Eleven", email="v11m@eleven.leviii")
    for path in (
        "/api/v1/eleven/money/forecast",
        "/api/v1/eleven/money/waterfall",
        "/api/v1/eleven/money/where",
        "/api/v1/eleven/money/goals",
        "/api/v1/eleven/money/heatmap",
    ):
        r = client.get(path, headers=_tok(owner))
        assert r.status_code == 200, path