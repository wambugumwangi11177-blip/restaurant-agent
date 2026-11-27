"""Scheduled owner report jobs."""
import json

import models
from services.owner_reports import run_daily_report
from services.owner_prefs import read_reports_past
from tests.test_storekeeper_foundation import _tenant


def test_daily_report_appends_list_and_notification(client, db_session):
    _, owner, restaurant = _tenant(db_session, "Eleven", "owner-reports@eleven.leviii")
    run_daily_report(db_session, restaurant.id)
    db_session.refresh(restaurant)
    past = read_reports_past(restaurant)
    assert past and past[0]["kind"] == "daily"
    notes = (
        db_session.query(models.Notification)
        .filter(models.Notification.user_id == owner.id, models.Notification.title == "Daily report ready")
        .count()
    )
    assert notes >= 1