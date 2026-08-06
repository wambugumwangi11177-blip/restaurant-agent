"""
Staff roster and shift tracking.

`StaffMember` and `LaborShift` shipped with the labor-intelligence work and had
NO writer anywhere in the codebase — not even in populate_production.py, which
seeds everything else. So `ai/labor/intelligence.py` returned its
`_empty_response()` on every restaurant without exception, and
`ai/roi/savings.py` always priced "hours saved" at its
DEFAULT_HOURLY_RATE_CENTS constant instead of at real wages.

These tests pin the write path and the two properties that keep labor cost
honest over time: clocking is idempotent, and a shift's cost is frozen at the
rate in force when it was worked.
"""

from datetime import date, timedelta

import auth
import models


def _owner(db_session, suffix):
    tenant = models.Tenant(name=f"T{suffix}")
    db_session.add(tenant)
    db_session.commit()
    user = models.User(
        tenant_id=tenant.id,
        email=f"boss{suffix}@e.com",
        hashed_password=auth.get_password_hash("x"),
        role=models.Role.ADMIN,
        token_version=0,
    )
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"R{suffix}", address="x")
    db_session.add_all([user, restaurant])
    db_session.commit()
    return auth.create_access_token({"sub": user.email, "ver": 0}), restaurant.id


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def _hire(client, token, name="Grace", rate=30000, title="Head Chef"):
    """rate is cents/hour — KES 300/hr by default."""
    r = client.post("/staff/", headers=_hdr(token), json={
        "name": name, "role_title": title, "hourly_rate": rate,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _schedule(client, token, staff_id, on=None):
    r = client.post("/staff/shifts/", headers=_hdr(token), json={
        "staff_member_id": staff_id,
        "shift_date": str(on or date.today()),
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ── Roster ───────────────────────────────────────────────────────────────────

def test_hire_list_and_deactivate(client, db_session):
    token, _ = _owner(db_session, "roster")
    staff_id = _hire(client, token, "Grace", 30000)

    listed = client.get("/staff/", headers=_hdr(token)).json()
    assert [s["name"] for s in listed] == ["Grace"]
    assert listed[0]["hourly_rate"] == 30000

    client.delete(f"/staff/{staff_id}", headers=_hdr(token))
    assert client.get("/staff/", headers=_hdr(token)).json() == []
    # Soft delete: their shift history is the restaurant's labor cost history.
    with_inactive = client.get("/staff/?include_inactive=true", headers=_hdr(token)).json()
    assert len(with_inactive) == 1
    assert with_inactive[0]["is_active"] is False


def test_roster_writes_are_admin_only(client, db_session):
    token, rid = _owner(db_session, "rbac")
    waiter = models.User(
        tenant_id=db_session.get(models.Restaurant, rid).tenant_id,
        email="w@e.com", hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF, token_version=0,
    )
    db_session.add(waiter)
    db_session.commit()
    staff_token = auth.create_access_token({"sub": waiter.email, "ver": 0})

    r = client.post("/staff/", headers=_hdr(staff_token),
                    json={"name": "X", "hourly_rate": 1})
    assert r.status_code == 403
    # Reading the roster is fine — the floor needs to see who's on.
    assert client.get("/staff/", headers=_hdr(staff_token)).status_code == 200


def test_negative_wage_rejected(client, db_session):
    token, _ = _owner(db_session, "wage")
    r = client.post("/staff/", headers=_hdr(token),
                    json={"name": "Y", "hourly_rate": -100})
    assert r.status_code == 400


def test_cannot_see_another_restaurants_staff(client, db_session):
    token_a, _ = _owner(db_session, "sa")
    token_b, _ = _owner(db_session, "sb")
    _hire(client, token_b, "Theirs")

    assert client.get("/staff/", headers=_hdr(token_a)).json() == []


# ── Clocking ─────────────────────────────────────────────────────────────────

def test_clock_in_then_out_computes_hours_and_cost(client, db_session):
    token, _ = _owner(db_session, "clock")
    staff_id = _hire(client, token, rate=30000)
    shift_id = _schedule(client, token, staff_id)

    client.post(f"/staff/shifts/{shift_id}/clock-in", headers=_hdr(token))
    out = client.post(f"/staff/shifts/{shift_id}/clock-out", headers=_hdr(token)).json()

    assert out["actual_start"] is not None
    assert out["actual_end"] is not None
    assert out["actual_hours"] >= 0
    # hourly_rate is cents/hour, so hours × rate is already cents.
    assert out["labor_cost"] == int(round(out["actual_hours"] * 30000))


def test_clock_in_is_idempotent(client, db_session):
    """Re-stamping would shorten the shift and undercount labor cost."""
    token, _ = _owner(db_session, "idem_in")
    shift_id = _schedule(client, token, _hire(client, token))

    first = client.post(f"/staff/shifts/{shift_id}/clock-in", headers=_hdr(token)).json()
    again = client.post(f"/staff/shifts/{shift_id}/clock-in", headers=_hdr(token)).json()
    assert first["actual_start"] == again["actual_start"]


def test_clock_out_is_idempotent(client, db_session):
    token, _ = _owner(db_session, "idem_out")
    shift_id = _schedule(client, token, _hire(client, token))

    client.post(f"/staff/shifts/{shift_id}/clock-in", headers=_hdr(token))
    first = client.post(f"/staff/shifts/{shift_id}/clock-out", headers=_hdr(token)).json()
    again = client.post(f"/staff/shifts/{shift_id}/clock-out", headers=_hdr(token)).json()
    assert first["actual_end"] == again["actual_end"]
    assert first["labor_cost"] == again["labor_cost"]


def test_cannot_clock_out_without_clocking_in(client, db_session):
    token, _ = _owner(db_session, "noin")
    shift_id = _schedule(client, token, _hire(client, token))
    r = client.post(f"/staff/shifts/{shift_id}/clock-out", headers=_hdr(token))
    assert r.status_code == 400


def test_a_raise_does_not_rewrite_past_labor_cost(client, db_session):
    """
    Recomputing historical cost from the current wage would move last month's
    labor cost % under the owner's feet every time someone got a raise.
    """
    token, _ = _owner(db_session, "raise")
    staff_id = _hire(client, token, rate=20000)
    shift_id = _schedule(client, token, staff_id)

    client.post(f"/staff/shifts/{shift_id}/clock-in", headers=_hdr(token))
    worked = client.post(f"/staff/shifts/{shift_id}/clock-out", headers=_hdr(token)).json()
    original_cost = worked["labor_cost"]

    client.put(f"/staff/{staff_id}", headers=_hdr(token), json={"hourly_rate": 99999})

    shifts = client.get("/staff/shifts/", headers=_hdr(token)).json()
    assert shifts[0]["labor_cost"] == original_cost


def test_scheduled_hours_computed_and_bad_window_rejected(client, db_session):
    from datetime import datetime
    token, _ = _owner(db_session, "sched")
    staff_id = _hire(client, token)
    start = datetime(2026, 8, 6, 9, 0, 0)

    ok = client.post("/staff/shifts/", headers=_hdr(token), json={
        "staff_member_id": staff_id,
        "shift_date": "2026-08-06",
        "scheduled_start": start.isoformat(),
        "scheduled_end": (start + timedelta(hours=8)).isoformat(),
    })
    assert ok.status_code == 200
    assert ok.json()["scheduled_hours"] == 8.0

    bad = client.post("/staff/shifts/", headers=_hdr(token), json={
        "staff_member_id": staff_id,
        "shift_date": "2026-08-06",
        "scheduled_start": start.isoformat(),
        "scheduled_end": (start - timedelta(hours=1)).isoformat(),
    })
    assert bad.status_code == 400


def test_cannot_schedule_another_restaurants_staff(client, db_session):
    token_a, _ = _owner(db_session, "xa")
    token_b, _ = _owner(db_session, "xb")
    their_staff = _hire(client, token_b, "Theirs")

    r = client.post("/staff/shifts/", headers=_hdr(token_a), json={
        "staff_member_id": their_staff, "shift_date": str(date.today()),
    })
    assert r.status_code == 404


# ── The point of the whole change ────────────────────────────────────────────

def test_labor_intelligence_stops_returning_empty(client, db_session):
    from ai.labor.intelligence import get_labor_intelligence

    token, rid = _owner(db_session, "labor")
    staff_id = _hire(client, token, rate=30000)
    shift_id = _schedule(client, token, staff_id)
    client.post(f"/staff/shifts/{shift_id}/clock-in", headers=_hdr(token))
    client.post(f"/staff/shifts/{shift_id}/clock-out", headers=_hdr(token))

    result = get_labor_intelligence(db_session, rid)
    summary = result["summary"]
    # `labor_status: "NO_DATA"` and `shifts_logged: 0` are exactly what
    # _empty_response() returns, and before this write path existed there was no
    # way to reach anything else — whatever the restaurant did.
    assert summary["labor_status"] != "NO_DATA"
    assert summary["shifts_logged"] == 1
    assert summary["total_hours_30d"] >= 0
    assert result["staff_productivity"], "a clocked shift must produce a productivity row"
