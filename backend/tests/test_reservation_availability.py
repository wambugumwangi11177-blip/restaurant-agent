"""
Real conflict/capacity logic for table booking (ai/reservation_optimizer.py).
The 6 scenarios verified by hand during Phase 1, now permanent.
"""

from datetime import date, time
import models
from ai.reservation_optimizer import find_available_tables


def _seed(db_session):
    tenant = models.Tenant(name="Availability Tenant")
    db_session.add(tenant)
    db_session.commit()
    r = models.Restaurant(id=1, tenant_id=tenant.id, name="Test Bistro", address="x")
    t_small = models.Table(restaurant_id=1, table_number=1, capacity=2)
    t_big = models.Table(restaurant_id=1, table_number=2, capacity=6)
    db_session.add_all([r, t_small, t_big])
    db_session.commit()
    return t_small, t_big


TARGET_DATE = date(2026, 7, 10)


def test_empty_slate_returns_smallest_fit_first(db_session):
    t_small, t_big = _seed(db_session)
    avail = find_available_tables(db_session, 1, party_size=2, reservation_date=TARGET_DATE, reservation_time=time(19, 0))
    assert avail[0]["table_id"] == t_small.id


def test_party_too_big_returns_nothing(db_session):
    _seed(db_session)
    avail = find_available_tables(db_session, 1, party_size=10, reservation_date=TARGET_DATE, reservation_time=time(19, 0))
    assert avail == []


def _book_small_table(db_session, t_small):
    res = models.Reservation(
        restaurant_id=1, table_id=t_small.id, customer_name="Jane",
        party_size=2, reservation_date=TARGET_DATE, reservation_time=time(19, 0),
        duration_minutes=90, status=models.ReservationStatus.CONFIRMED,
    )
    db_session.add(res)
    db_session.commit()


def test_exact_overlap_excludes_booked_table(db_session):
    t_small, t_big = _seed(db_session)
    _book_small_table(db_session, t_small)

    avail = find_available_tables(db_session, 1, party_size=2, reservation_date=TARGET_DATE, reservation_time=time(19, 0))
    ids = [a["table_id"] for a in avail]
    assert t_small.id not in ids
    assert t_big.id in ids


def test_partial_overlap_excludes_booked_table(db_session):
    t_small, t_big = _seed(db_session)
    _book_small_table(db_session, t_small)

    avail = find_available_tables(db_session, 1, party_size=2, reservation_date=TARGET_DATE, reservation_time=time(19, 30))
    assert t_small.id not in [a["table_id"] for a in avail]


def test_adjacent_non_overlapping_slot_is_available(db_session):
    t_small, t_big = _seed(db_session)
    _book_small_table(db_session, t_small)

    avail = find_available_tables(db_session, 1, party_size=2, reservation_date=TARGET_DATE, reservation_time=time(20, 30))
    assert t_small.id in [a["table_id"] for a in avail]


def test_different_date_is_fully_available(db_session):
    t_small, t_big = _seed(db_session)
    _book_small_table(db_session, t_small)

    avail = find_available_tables(db_session, 1, party_size=2, reservation_date=date(2026, 7, 11), reservation_time=time(19, 0))
    assert t_small.id in [a["table_id"] for a in avail]
