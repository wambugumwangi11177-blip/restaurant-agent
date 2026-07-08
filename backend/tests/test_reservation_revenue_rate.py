"""
`avg_spend_per_guest` — the rate three money estimates are built on.

Until 2026-07-08 it divided *all* dine-in revenue by *reserved* guests only.
Most covers are walk-ins, so the denominator was a fraction of the people who
generated the numerator and the rate was inflated by 1 / (reservation share of
covers). On a smoke dataset it read KES 5,845 "per guest" at a venue whose
average check was ~KES 244.

`Order` carries no guest count, so covers are now estimated as
`dine_in_orders x avg_party_size`. Every dine-in order is one check, i.e. one
party; the reservation book supplies people-per-party. The estimate is labelled
as one in the payload.

The rate feeds:
  • revenue_impact.estimated_revenue_lost  (no_show_seats x rate)
  • table_utilization per-table revenue
  • overbooking.potential_recovery
"""

from datetime import datetime, time, timedelta

import pytest

import models
from ai import reservation_optimizer
from ai.analysis_clock import ANCHOR_SAMPLE_SIZE
from ai.reservation_optimizer import DEFAULT_PARTY_SIZE

ANCHOR = datetime(2026, 7, 1, 12, 0, 0)
N_ORDERS = ANCHOR_SAMPLE_SIZE + 10        # 40 — keeps the analysis anchor in-window
CHECK_CENTS = 24_400                      # KES 244 average check


def _restaurant(db):
    db.add(models.Restaurant(id=1, tenant_id=None, name="Covers", address="x"))
    db.commit()


def _dine_in_orders(db, n=N_ORDERS, total=CHECK_CENTS, days_ago=2):
    for _ in range(n):
        db.add(models.Order(
            restaurant_id=1, status=models.OrderStatus.SERVED,
            order_type=models.OrderType.DINE_IN,
            payment_method=models.PaymentMethod.CASH, is_paid=True,
            total=total, created_at=ANCHOR - timedelta(days=days_ago),
        ))
    db.commit()


def _reservation(db, party_size, status=models.ReservationStatus.COMPLETED, days_ago=2):
    db.add(models.Reservation(
        restaurant_id=1, customer_name="G", customer_phone="1", party_size=party_size,
        reservation_date=(ANCHOR - timedelta(days=days_ago)).date(),
        reservation_time=time(19, 0), status=status,
    ))
    db.commit()


def _impact(db):
    return reservation_optimizer.get_reservation_insights(db, 1)["revenue_impact"]


def test_rate_counts_every_party_that_ate_not_only_the_ones_that_booked(db_session):
    """
    40 dine-in checks of KES 244, but only ONE table booked (a 2-top).

    Old denominator: 2 reserved guests   -> 40 * 24400 / 2   = KES 4,880/guest.
    New denominator: 40 checks x 2 avg   -> 40 * 24400 / 80  = KES 122/guest.

    The venue's average check is KES 244 for a party of two. KES 122/head is the
    only one of those two numbers a restaurateur would recognise.
    """
    _restaurant(db_session)
    _dine_in_orders(db_session)
    _reservation(db_session, party_size=2)

    impact = _impact(db_session)

    assert impact["dine_in_orders"] == N_ORDERS
    assert impact["avg_party_size"] == 2.0
    assert impact["estimated_covers"] == N_ORDERS * 2
    assert impact["avg_spend_per_guest"] == CHECK_CENTS // 2      # 12200 cents = KES 122

    # The discredited figure — revenue over reserved guests alone.
    assert impact["avg_spend_per_guest"] != (N_ORDERS * CHECK_CENTS) // 2


def test_rate_scales_with_party_size_not_with_booking_volume(db_session):
    """
    Doubling the number of *bookings* must not change spend per head; doubling
    the party size must halve it. That is what makes it a rate.
    """
    _restaurant(db_session)
    _dine_in_orders(db_session)
    _reservation(db_session, party_size=2)
    one_booking = _impact(db_session)["avg_spend_per_guest"]

    _reservation(db_session, party_size=2)   # same party size, another booking
    two_bookings = _impact(db_session)["avg_spend_per_guest"]
    assert two_bookings == one_booking, "spend per head moved when only booking count changed"

    _reservation(db_session, party_size=8)   # pushes avg party 2,2,8 -> 4.0
    bigger_parties = _impact(db_session)["avg_spend_per_guest"]
    assert bigger_parties == CHECK_CENTS // 4
    assert bigger_parties < one_booking, "bigger parties must lower spend per head"


def test_no_reservations_at_all_falls_back_to_a_default_party_size(db_session):
    """A walk-in-only venue still gets a sane rate instead of dividing by zero."""
    _restaurant(db_session)
    _dine_in_orders(db_session)
    _reservation(db_session, party_size=3, status=models.ReservationStatus.CANCELLED)

    impact = _impact(db_session)
    assert impact["avg_party_size"] == DEFAULT_PARTY_SIZE
    assert impact["estimated_covers"] == int(N_ORDERS * DEFAULT_PARTY_SIZE)
    assert impact["avg_spend_per_guest"] == int(CHECK_CENTS / DEFAULT_PARTY_SIZE)


def test_payload_declares_the_covers_are_estimated(db_session):
    """
    The reasoning layer grounds narrative numbers against this payload, and the
    UI renders the rate. Both need to know covers were inferred, not counted.
    """
    _restaurant(db_session)
    _dine_in_orders(db_session)
    _reservation(db_session, party_size=2)

    impact = _impact(db_session)
    assert impact["covers_are_estimated"] is True
    # Inputs present so the figure can be re-derived and audited.
    assert impact["avg_spend_per_guest"] * impact["estimated_covers"] == pytest.approx(
        impact["total_dine_in_revenue"], rel=0.01
    )


def test_downstream_no_show_loss_uses_the_corrected_rate(db_session):
    """
    estimated_revenue_lost = no_show_seats x rate. With the old rate it was
    inflated by the same factor, and it is what ops_manager surfaces as a risk.
    """
    _restaurant(db_session)
    _dine_in_orders(db_session)
    _reservation(db_session, party_size=2)
    _reservation(db_session, party_size=4, status=models.ReservationStatus.NO_SHOW)

    impact = _impact(db_session)
    assert impact["no_show_seats_lost"] == 4
    assert impact["estimated_revenue_lost"] == 4 * impact["avg_spend_per_guest"]
    # 4 seats at ~one head's spend cannot exceed a month of dine-in revenue.
    assert impact["estimated_revenue_lost"] < impact["total_dine_in_revenue"]


def test_loss_can_no_longer_exceed_total_revenue(db_session):
    """
    The reductio the old formula permitted: one 2-top booked, one 10-top no-show,
    a busy month of walk-ins. Old rate = revenue/2, so a 10-seat no-show "cost"
    five times the restaurant's entire dine-in revenue.
    """
    _restaurant(db_session)
    _dine_in_orders(db_session)
    _reservation(db_session, party_size=2)
    _reservation(db_session, party_size=10, status=models.ReservationStatus.NO_SHOW)

    impact = _impact(db_session)
    assert impact["estimated_revenue_lost"] <= impact["total_dine_in_revenue"]
    assert impact["lost_pct_of_dine_revenue"] <= 100.0
