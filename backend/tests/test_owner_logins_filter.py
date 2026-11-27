"""Settings logins scoped to active restaurant."""
import models
from tests.test_storekeeper_foundation import _auth, _tenant, _token


def test_logins_exclude_other_restaurant_and_superadmin(client, db_session):
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-logins@eleven.leviii")
    other = models.Restaurant(tenant_id=tenant.id, name="Empty wall", address="x")
    db_session.add(other)
    db_session.flush()
    jack = models.User(
        tenant_id=tenant.id,
        email="jack@eleven.leviii",
        hashed_password="x",
        role=models.Role.STAFF,
        staff_role=models.StaffRole.STOCKKEEPER,
        is_active=True,
        active_restaurant_id=restaurant.id,
    )
    jack_empty = models.User(
        tenant_id=tenant.id,
        email="jack-empty@eleven.leviii",
        hashed_password="x",
        role=models.Role.STAFF,
        staff_role=models.StaffRole.STOCKKEEPER,
        is_active=True,
        active_restaurant_id=other.id,
    )
    sa = models.User(
        tenant_id=tenant.id,
        email="wambugu@leviii.ai",
        hashed_password="x",
        role=models.Role.SUPERADMIN,
        staff_role=models.StaffRole.OWNER,
        is_active=True,
        active_restaurant_id=restaurant.id,
    )
    db_session.add_all([jack, jack_empty, sa])
    db_session.commit()
    resp = client.get("/api/v1/eleven/logins", headers=_auth(_token(owner)))
    assert resp.status_code == 200
    emails = {row["email"] for row in resp.json()}
    assert "jack@eleven.leviii" in emails
    assert "jack-empty@eleven.leviii" not in emails
    assert "wambugu@leviii.ai" not in emails