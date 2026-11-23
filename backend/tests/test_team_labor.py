"""Team schedule + roster tests."""
from datetime import date, timedelta

import auth
import models
from services.labor_schedule import (
    check_team_rules,
    compact_schedule_labels,
    longest_consecutive_run,
    materialize_week,
    weekly_hours_for_member,
)
from tests.test_storekeeper_foundation import _auth, _tenant, _token


def test_no_login_staff_roles_rejected(client, db_session):
    _, owner, _ = _tenant(db_session, "Eleven", "owner@eleven.leviii")
    response = client.post(
        "/api/v1/staff/",
        headers=_auth(_token(owner)),
        json={
            "name": "Sam Waiter",
            "role_title": "waiter",
            "create_login": True,
            "email": "waiter@test.leviii",
            "password": "TestPass123!",
            "staff_role": "waiter",
        },
    )
    assert response.status_code == 400


def test_roster_member_without_login(client, db_session):
    _, owner, _ = _tenant(db_session, "Eleven", "owner@eleven.leviii")
    response = client.post(
        "/api/v1/team/roster",
        headers=_auth(_token(owner)),
        json={"name": "Joy", "role_title": "waiter", "daily_pay_rate_cents": 150000},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Joy"
    assert body["has_login"] is False


def test_weekly_schedule_materializes_labor_shift(client, db_session):
    _, owner, restaurant = _tenant(db_session, "Eleven", "owner@eleven.leviii")
    roster = client.post(
        "/api/v1/team/roster",
        headers=_auth(_token(owner)),
        json={"name": "Pat", "role_title": "waiter", "daily_pay_rate_cents": 120000},
    ).json()
    put = client.put(
        "/api/v1/team/weekly-slots",
        headers=_auth(_token(owner)),
        json={
            "slots": [
                {
                    "staff_member_id": roster["id"],
                    "weekday": date.today().weekday(),
                    "start_time": "09:00",
                    "end_time": "17:00",
                }
            ]
        },
    )
    assert put.status_code == 200
    assert put.json().get("shifts_materialized", 0) >= 1
    db_session.expire_all()
    shift = db_session.query(models.LaborShift).filter(
        models.LaborShift.staff_member_id == roster["id"],
        models.LaborShift.shift_date == date.today(),
    ).first()
    assert shift is not None
    assert shift.scheduled_hours == 8
    assert weekly_hours_for_member(db_session, restaurant.id, roster["id"]) == 8


def test_team_rules_weekly_hours_warning(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "owner@eleven.leviii")
    member = models.StaffMember(restaurant_id=restaurant.id, name="Long", role_title="waiter")
    db_session.add(member)
    db_session.commit()
    warnings = check_team_rules(
        db_session,
        restaurant.id,
        {
            member.id: [
                {"weekday": i, "start_time": "08:00", "end_time": "18:00"}
                for i in range(6)
            ]
        },
    )
    assert any("hours" in w.lower() for w in warnings)


def test_compact_schedule_labels_group_days():
    slots = [{"weekday": i, "start_time": "09:00", "end_time": "17:00"} for i in range(4)]
    labels = compact_schedule_labels(slots)
    assert labels == ["Mon–Thu 09:00–17:00"]
    hours = sum(8 for _ in slots)
    assert hours == 32


def test_longest_consecutive_run():
    assert longest_consecutive_run({0, 1, 2, 3}) == 4
    assert longest_consecutive_run({0, 2, 4}) == 1


def test_consecutive_streak_rule_warning(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "owner3@eleven.leviii")
    member = models.StaffMember(restaurant_id=restaurant.id, name="Busy", role_title="waiter")
    db_session.add(member)
    db_session.commit()
    warnings = check_team_rules(
        db_session,
        restaurant.id,
        {
            member.id: [{"weekday": i, "start_time": "09:00", "end_time": "17:00"} for i in range(7)],
        },
    )
    assert any("in a row" in w for w in warnings)