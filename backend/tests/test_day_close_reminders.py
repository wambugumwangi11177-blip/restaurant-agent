from datetime import datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

import models
from bill_schedule import business_today
from services.day_close_reminders import duty_cards_for_viewer, process_day_close_reminders
from tests.test_storekeeper_foundation import _tenant


def test_duty_card_for_stockkeeper_after_close_time(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "owner-dc@eleven.leviii")
    restaurant.day_close_reminder_time = "00:00"
    db_session.commit()
    jack = models.User(
        tenant_id=restaurant.tenant_id,
        email="jack-dc@eleven.leviii",
        hashed_password="x",
        role=models.Role.STAFF,
        staff_role=models.StaffRole.STOCKKEEPER,
        is_active=True,
    )
    db_session.add(jack)
    db_session.commit()
    nairobi = datetime.now(ZoneInfo("Africa/Nairobi"))
    with patch("services.day_close_reminders.datetime") as mock_dt:
        mock_dt.now.return_value = nairobi
        mock_dt.combine = datetime.combine
        cards = duty_cards_for_viewer(db_session, restaurant, jack)
    assert any(c["kind"] == "day_close_stock" for c in cards)


def test_reminder_notify_stockkeeper(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "owner-rem@eleven.leviii")
    restaurant.day_close_reminder_time = "00:00"
    db_session.commit()
    jack = models.User(
        tenant_id=restaurant.tenant_id,
        email="jack-rem@eleven.leviii",
        hashed_password="x",
        role=models.Role.STAFF,
        staff_role=models.StaffRole.STOCKKEEPER,
        is_active=True,
    )
    db_session.add(jack)
    db_session.commit()
    nairobi = datetime.now(ZoneInfo("Africa/Nairobi"))
    with patch("services.day_close_reminders.datetime") as mock_dt:
        mock_dt.now.return_value = nairobi
        mock_dt.combine = datetime.combine
        sent = process_day_close_reminders(db_session, restaurant.id)
    assert sent >= 1
    rows = db_session.query(models.Notification).filter_by(user_id=jack.id, event_type="day_close_reminder").all()
    assert rows

def test_reminders_repeat_every_thirty_minutes_until_closed(db_session):
    _, _, restaurant = _tenant(db_session, "Eleven", "owner-rep@eleven.leviii")
    jack = models.User(
        tenant_id=restaurant.tenant_id,
        email="jack-rep@eleven.leviii",
        hashed_password="x",
        role=models.Role.STAFF,
        staff_role=models.StaffRole.STOCKKEEPER,
        is_active=True,
    )
    db_session.add(jack)
    db_session.commit()
    day = business_today()
    nairobi = ZoneInfo("Africa/Nairobi")

    def run_at(hour: int, minute: int) -> int:
        with patch("services.day_close_reminders.datetime") as mock_dt:
            mock_dt.now.return_value = datetime.combine(day, time(hour, minute), tzinfo=nairobi)
            mock_dt.combine = datetime.combine
            return process_day_close_reminders(db_session, restaurant.id)

    assert run_at(21, 59) == 0
    assert run_at(22, 0) == 1
    assert run_at(22, 10) == 0
    assert run_at(22, 30) == 1
    assert run_at(22, 45) == 0
    assert run_at(23, 0) == 1
    assert run_at(23, 30) == 1
    assert run_at(23, 59) == 0


def test_test_stack_hook_moves_the_close_time_and_fires_reminders(client, db_session, monkeypatch):
    from tests.test_storekeeper_foundation import _add_staff, _auth, _token

    monkeypatch.setenv("SEED_TEST_DATA", "1")
    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-hook@eleven.leviii")
    jack = _add_staff(db_session, tenant, restaurant, "jack-hook@eleven.leviii", models.StaffRole.STOCKKEEPER)
    denied = client.post("/api/v1/test/day-close-reminders", headers=_auth(_token(jack)), json={"reminder_time": "00:00"})
    assert denied.status_code == 403
    fired = client.post("/api/v1/test/day-close-reminders", headers=_auth(_token(owner)), json={"reminder_time": "00:00"})
    assert fired.status_code == 200
    assert fired.json()["sent"] >= 1
    db_session.refresh(restaurant)
    assert restaurant.day_close_reminder_time == "00:00"
    bad = client.post("/api/v1/test/day-close-reminders", headers=_auth(_token(owner)), json={"reminder_time": "25:99"})
    assert bad.status_code == 422


def test_day_close_has_one_reminder_set_not_two(client, db_session):
    from tests.test_storekeeper_foundation import _add_staff, _auth, _token

    tenant, owner, restaurant = _tenant(db_session, "Eleven", "owner-one@eleven.leviii")
    restaurant.day_close_reminder_time = "00:00"
    db_session.commit()
    amina = _add_staff(db_session, tenant, restaurant, "amina-one@eleven.leviii", models.StaffRole.CONTROLLER)
    db_session.add(models.StaffSetupProgress(
        user_id=amina.id, restaurant_id=restaurant.id, updated_at=datetime.utcnow(),
        account_completed_at=datetime.utcnow(), questionnaire_completed_at=datetime.utcnow(), recipes_completed_at=datetime.utcnow(),
    ))
    db_session.commit()
    nairobi = datetime.now(ZoneInfo("Africa/Nairobi"))
    with patch("services.day_close_reminders.datetime") as mock_dt:
        mock_dt.now.return_value = nairobi
        mock_dt.combine = datetime.combine
        process_day_close_reminders(db_session, restaurant.id)
        inbox = client.get("/api/v1/store/approval-inbox", headers=_auth(_token(amina)))
    assert inbox.status_code == 200, inbox.text
    assert any(card["kind"] == "day_close_cash" for card in inbox.json()["pending"])
    assert db_session.query(models.ApprovalReminder).filter(models.ApprovalReminder.kind.like("day_close%")).count() == 0
    titles = [n.title for n in db_session.query(models.Notification).filter_by(user_id=amina.id).all()]
    assert titles == ["Close the day — cash"]
