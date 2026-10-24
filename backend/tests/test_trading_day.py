"""One trading day for sales, Home, break-even and the trend.

01:30 Nairobi is still the previous service. 14:00 is the calendar day.
Bookings stay on the calendar day either way.
"""
from datetime import datetime, time, timedelta

import models
from owner.home import compose_home
from owner.states import OwnerContext
from routers.ai_ask import _answer_revenue
from routers.overview import _performance, _summarize
from routers.reports import _range
from tests.fixtures import golden_restaurant as gr
from time_utils import trading_day, trading_window

AT_0130 = datetime(2026, 10, 23, 22, 30)   # Saturday 01:30 Nairobi; open service is Friday 23 Oct
AT_1400 = datetime(2026, 10, 24, 11, 0)    # Saturday 14:00 Nairobi
FRIDAY_NIGHT = datetime(2026, 10, 23, 19, 0)    # Friday 22:00 Nairobi, KES 16,340
AFTER_MIDNIGHT = datetime(2026, 10, 23, 21, 30)  # Saturday 00:30 Nairobi, KES 2,180
THURSDAY = datetime(2026, 10, 22, 12, 0)         # Thursday 15:00 Nairobi, KES 5,000


def test_open_periods_include_the_hour_after_midnight_and_closed_ones_do_not():
    assert trading_day(AT_0130).isoformat() == "2026-10-23"
    assert trading_day(AT_1400).isoformat() == "2026-10-24"

    today_start, today_end, today = trading_window("today", AT_0130)
    assert today.isoformat() == "2026-10-23"
    assert today_end == AT_0130
    assert today_start <= FRIDAY_NIGHT < today_end
    assert today_start <= AFTER_MIDNIGHT < today_end
    assert not (today_start <= THURSDAY < today_end)

    week_start, week_end, _week = trading_window("this_week", AT_0130)
    month_start, month_end, _month = trading_window("this_month", AT_0130)
    assert week_end == AT_0130 and month_end == AT_0130
    assert week_start <= AFTER_MIDNIGHT < week_end
    assert month_start <= AFTER_MIDNIGHT < month_end

    y_start, y_end, y_day = trading_window("yesterday", AT_0130)
    assert y_day.isoformat() == "2026-10-22"
    assert y_start <= THURSDAY < y_end
    assert not (y_start <= FRIDAY_NIGHT < y_end)

    afternoon_start, afternoon_end, afternoon = trading_window("today", AT_1400)
    assert afternoon.isoformat() == "2026-10-24"
    assert afternoon_end == AT_1400
    assert afternoon_start <= AFTER_MIDNIGHT < afternoon_end
    assert not (afternoon_start <= FRIDAY_NIGHT < afternoon_end)

    y2_start, y2_end, y2 = trading_window("yesterday", AT_1400)
    assert y2.isoformat() == "2026-10-23"
    assert y2_start <= FRIDAY_NIGHT < y2_end
    assert not (y2_start <= AFTER_MIDNIGHT < y2_end)

    # At 14:00 a rolling week still ends at the moment, and matches the old offset.
    start, end, _day = trading_window("7d", AT_1400)
    assert (start, end) == (AT_1400 - timedelta(days=7), AT_1400)
    start, end, _day = trading_window("1h", AT_0130)
    assert (start, end) == (AT_0130 - timedelta(hours=1), AT_0130)


def _freeze(monkeypatch, moment):
    monkeypatch.setattr("time_utils.utcnow", lambda: moment)
    monkeypatch.setattr("routers.overview.utcnow", lambda: moment)
    monkeypatch.setattr("owner.states.utcnow", lambda: moment)
    monkeypatch.setattr("routers.reports.utcnow", lambda: moment)


def _plant(db, g):
    pilau = g.items["Pilau"]
    gr.add_order(db, g, [(pilau, 1, 1_634_000)], FRIDAY_NIGHT)
    gr.add_order(db, g, [(pilau, 1, 218_000)], AFTER_MIDNIGHT)
    gr.add_order(db, g, [(pilau, 1, 500_000)], THURSDAY)
    db.add(models.Reservation(
        restaurant_id=g.rid, customer_name="Friday party", party_size=10,
        reservation_date=trading_day(AT_0130), reservation_time=time(19, 0),
        status=models.ReservationStatus.CONFIRMED,
    ))
    db.add(models.Reservation(
        restaurant_id=g.rid, customer_name="Saturday party", party_size=2,
        reservation_date=trading_day(AT_1400), reservation_time=time(13, 0),
        status=models.ReservationStatus.CONFIRMED,
    ))
    db.commit()


def _agree(db, g, moment, sales_kes, orders):
    ctx = OwnerContext(db, g.owner, g.restaurant)
    ctx.now = moment
    home = compose_home(ctx, "today")
    pulse = home["pulse"]
    assert pulse["sales_today"] == sales_kes
    assert pulse["orders_today"] == orders
    assert pulse["sales_in_period"] == sales_kes
    assert pulse["orders_in_period"] == orders
    assert pulse["trend_7d"][-1]["date"] == trading_day(moment).isoformat()
    assert pulse["trend_7d"][-1]["sales"] == sales_kes
    assert pulse["trend_7d"][-1]["orders"] == orders
    assert pulse["breakeven_at"]["sales_today_kes"] == sales_kes
    start, end = _range("daily")
    report = _summarize(db, g.rid, start, end)
    assert report["revenue"] == sales_kes and report["orders"] == orders
    window = trading_window("today", moment)
    overview = _summarize(db, g.rid, window[0], window[1])
    assert overview["revenue"] == sales_kes and overview["orders"] == orders
    trend = _performance(db, g.rid, moment)["revenue_trend"][-1]
    assert trend["revenue"] == sales_kes and trend["orders"] == orders
    what = _answer_revenue(db, g.rid, "How were sales today?")
    assert f"KES {sales_kes:,.0f}" in what["finding"]
    assert f"{orders} paid" in what["finding"]
    assert home["coming_up"]["bookings"]["covers_today"] == 2
    return home


def test_home_matches_the_trading_day_at_0130_and_1400(db_session, monkeypatch):
    g = gr.build_skeleton(db_session, now=datetime(2026, 9, 25, 10, 0), suffix="trade")
    gr.seed_pnl_month(db_session, g)
    _plant(db_session, g)

    _freeze(monkeypatch, AT_0130)
    _agree(db_session, g, AT_0130, 18_520.0, 2)
    yesterday = _answer_revenue(db_session, g.rid, "What did I sell yesterday?")
    assert "KES 5,000" in yesterday["finding"]
    assert "KES 16,340" not in yesterday["finding"]

    _freeze(monkeypatch, AT_1400)
    home = _agree(db_session, g, AT_1400, 2_180.0, 1)
    yesterday = _answer_revenue(db_session, g.rid, "What did I sell yesterday?")
    assert "KES 16,340" in yesterday["finding"]
    assert "KES 2,180" not in yesterday["finding"]
    assert home["pulse"]["breakeven_at"]["sales_today_kes"] == 2_180.0


def test_clean_dish_name_drops_a_portion_count_only():
    from ai.creative import clean_dish_name
    assert clean_dish_name("Samosa (2)") == "Samosa"
    assert clean_dish_name("Mandazi (3)") == "Mandazi"
    assert clean_dish_name("Nyama choma (goat)") == "Nyama choma (goat)"
    assert clean_dish_name("Review margin on Samosa (2)") == "Review margin on Samosa"


def test_no_show_count_carries_the_span_it_was_counted_over(db_session):
    from ai.home_specialists import collect
    from ai.reservation_optimizer import get_reservation_insights
    tenant = models.Tenant(name="No-show span")
    db_session.add(tenant)
    db_session.flush()
    restaurant = models.Restaurant(tenant_id=tenant.id, name="No-show span", address="Nairobi")
    db_session.add(restaurant)
    db_session.flush()
    for day in (datetime(2026, 8, 1).date(), datetime(2026, 10, 2).date()):
        db_session.add(models.Reservation(
            restaurant_id=restaurant.id, customer_name="Guest", party_size=2,
            reservation_date=day, status=models.ReservationStatus.NO_SHOW,
        ))
    db_session.commit()
    analysis = get_reservation_insights(db_session, restaurant.id)["no_show_analysis"]
    assert analysis["no_shows"] == 2
    assert analysis["period"] == "all recorded reservations from 2026-08-01 to 2026-10-02, not one day"
    cards, _states = collect(db_session, restaurant.id)
    title = next(card["title"] for card in cards if "no-show" in card["title"])
    assert analysis["period"] in title
    assert "one day" in title
