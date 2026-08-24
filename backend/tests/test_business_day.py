"""Operational 'today' is Africa/Nairobi, not UTC midnight.

Home / Orders / Sales disagreed because:
  • Home used the UTC date of the latest order
  • Orders used `new Date().toISOString().slice(0,10)` (UTC)
  • Sales used the latest day in the list and forgot to divide cents by 100

These tests lock the backend half of that contract.
"""

from datetime import date, datetime, timedelta

import models
from time_utils import (
    business_today,
    utc_naive_range_for_day,
)


def test_nairobi_day_starts_at_21_00_utc():
    start, end = utc_naive_range_for_day(date(2026, 8, 23))
    assert start == datetime(2026, 8, 22, 21, 0, 0)
    assert end == datetime(2026, 8, 23, 21, 0, 0)


def test_business_today_follows_nairobi_not_utc():
    # 22 Aug 2026 21:30 UTC is already 23 Aug 00:30 in Nairobi.
    just_after_eat_midnight = datetime(2026, 8, 22, 21, 30, 0)
    assert business_today(just_after_eat_midnight) == date(2026, 8, 23)
    # Same instant, still 22 Aug in UTC.
    assert just_after_eat_midnight.date() == date(2026, 8, 22)


def test_dashboard_today_uses_nairobi_window(db_session):
    from ai import ops_manager

    db_session.add(models.Restaurant(id=1, tenant_id=None, name="Kibanda", address="x"))
    db_session.commit()

    today = business_today()
    start, end = utc_naive_range_for_day(today)
    # One order just inside today's Nairobi window, one just before it.
    db_session.add(models.Order(
        restaurant_id=1, status=models.OrderStatus.SERVED,
        payment_method=models.PaymentMethod.CASH, is_paid=True,
        total=50_000, created_at=start,
    ))
    db_session.add(models.Order(
        restaurant_id=1, status=models.OrderStatus.SERVED,
        payment_method=models.PaymentMethod.CASH, is_paid=True,
        total=90_000, created_at=start - timedelta(seconds=1),
    ))
    db_session.commit()

    stats = ops_manager.get_operations_dashboard(db_session, 1)["quick_stats"]
    assert stats["snapshot_date"] == today.isoformat()
    assert stats["timezone"] == "Africa/Nairobi"
    assert stats["today_revenue"] == 50_000
    assert stats["today_orders"] == 1
    assert stats["yesterday_revenue"] == 90_000


def test_alerts_humanize_and_dedupe():
    from ai.ops_manager import _aggregate_alerts

    inventory = {
        "alerts": [
            {"item": "Bacon", "message": "High spoilage risk (80%).", "severity": "warning", "action": "use_or_promote"},
            {"item": "Bacon", "message": "High spoilage risk (80%).", "severity": "warning", "action": "use_or_promote"},
            {"item": "Milk", "message": "High spoilage risk (80%).", "severity": "warning", "action": "use_or_promote"},
        ]
    }
    alerts = _aggregate_alerts({}, {}, inventory, {})
    assert len(alerts) == 2
    assert alerts[0]["action"] == "Use or promote before it spoils"
    assert alerts[0]["message"].startswith("Bacon")
    assert alerts[1]["message"].startswith("Milk")
    assert "use_or_promote" not in alerts[0]["action"]
