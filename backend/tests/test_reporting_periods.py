from datetime import date

from reporting import period_for


def test_reporting_periods_are_calendar_boundaries_in_nairobi():
    weekly = period_for("weekly", date(2026, 9, 15))
    monthly = period_for("monthly", date(2026, 2, 7))
    yearly = period_for("yearly", date(2026, 2, 7))
    assert weekly.start.isoformat() == "2026-09-14T00:00:00+03:00"
    assert weekly.end.isoformat() == "2026-09-21T00:00:00+03:00"
    assert monthly.end.isoformat() == "2026-03-01T00:00:00+03:00"
    assert yearly.end.isoformat() == "2027-01-01T00:00:00+03:00"
