from datetime import datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

import models
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