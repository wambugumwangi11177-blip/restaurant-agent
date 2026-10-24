"""Owner answers must preserve the actual analytics contracts, not just HTTP 200."""
from tests.test_home_attention_intelligence import restaurant  # noqa: F401
from routers.ai_ask import _answer_menu, _answer_kitchen, _answer_staff, _answer_profit, _answer_revenue


def test_menu_answer_uses_real_classified_items(db_session, restaurant):
    from ai.menu_engineer import get_menu_engineering
    _, r = restaurant
    analysis = get_menu_engineering(db_session, r.id)
    stars = [row for row in analysis["matrix"] if row["classification"] == "Star"]
    assert stars
    answer = _answer_menu(db_session, r.id, "Which dishes should I promote?")
    assert f"{len(stars)} star" in answer["finding"]
    assert any(stars[0]["name"] in step["action"] for step in answer["steps"])


def test_missing_kitchen_measurements_never_claim_on_pace(db_session, restaurant):
    _, r = restaurant
    answer = _answer_kitchen(db_session, r.id, "Is the kitchen slow?")
    assert answer["data"]["available"] is False
    assert "on pace" not in answer["finding"].lower()


def test_staff_answer_reads_nested_summary_and_preserves_zero(monkeypatch):
    from ai.labor import intelligence
    monkeypatch.setattr(intelligence, "get_labor_intelligence", lambda *_: {
        "summary": {"labor_pct": 0.0, "shifts_logged": 2, "total_revenue_30d": 10000},
        "recommendations": [],
    })
    answer = _answer_staff(None, 1, "What is labor cost?")
    assert "0.0%" in answer["finding"]


def test_profit_answer_reports_real_leaks(db_session, restaurant):
    from ai.profit.intelligence import get_profit_intelligence
    _, r = restaurant
    analysis = get_profit_intelligence(db_session, r.id)
    assert analysis["profit_leaks"]
    answer = _answer_profit(db_session, r.id, "Where am I losing money?")
    assert analysis["profit_leaks"][0]["item_name"] in answer["finding"]
    assert answer["impact"] != "—"


def test_reservations_preserve_rate_and_estimated_money(db_session, restaurant):
    from datetime import date
    import models
    from routers.ai_ask import _answer_bookings
    _, r = restaurant
    db_session.add_all([
        models.Reservation(restaurant_id=r.id, customer_name='Recorded guest', party_size=2,
                           reservation_date=date(2026, 9, 10), status=models.ReservationStatus.NO_SHOW),
        models.Reservation(restaurant_id=r.id, customer_name='Recorded guest', party_size=2,
                           reservation_date=date(2026, 9, 11), status=models.ReservationStatus.COMPLETED),
    ])
    db_session.commit()
    answer = _answer_bookings(db_session, r.id, 'What is the no-show rate?')
    assert '50.0%' in answer['finding']
    assert '2 reservations' in answer['finding']
    assert answer['impact'].startswith('Estimated historical')
    assert answer['data']['no_show_analysis']['no_shows'] == 1


def test_pricing_uses_real_item_name_and_prices(db_session, restaurant):
    from ai.pricing.recommendations import get_pricing_intelligence
    from routers.ai_ask import _answer_pricing
    _, r = restaurant
    analysis = get_pricing_intelligence(db_session, r.id)
    assert analysis['recommendations']
    first = analysis['recommendations'][0]
    answer = _answer_pricing(db_session, r.id, 'Which prices should change?')
    assert first['item_name'] in answer['finding']
    assert '?' not in answer['finding']
    assert 'does not change prices' in answer['recommendation']


def test_today_bookings_exclude_cancelled_and_foreign_rows(db_session, restaurant):
    import models
    from routers.ai_ask import _answer_bookings
    from routers.overview import _eat_now
    _, r = restaurant
    for status, covers in [(models.ReservationStatus.CONFIRMED, 3), (models.ReservationStatus.CANCELLED, 9)]:
        db_session.add(models.Reservation(restaurant_id=r.id, customer_name='Guest', party_size=covers,
                       reservation_date=_eat_now().date(), status=status))
    db_session.commit()
    answer = _answer_bookings(db_session, r.id, "Who's booked tonight?")
    assert answer['data']['covers'] == 3
    assert len(answer['steps']) == 1
    assert answer['data']['narrative_allowed'] is False


def _weekly_row(day, avg_revenue, avg_orders, total_orders, days_sampled):
    """A row shaped exactly as ai/revenue_forecaster.py builds weekly_pattern."""
    return {"day": day, "avg_revenue": avg_revenue, "avg_orders": avg_orders,
            "total_revenue": avg_revenue * days_sampled, "total_orders": total_orders,
            "days_sampled": days_sampled}


def test_slow_days_answer_is_specific_and_grounded(monkeypatch, db_session, restaurant):
    from ai import revenue_forecaster
    _, r = restaurant
    # weekly_pattern is a TOP-LEVEL key of the forecaster's response. A fixture
    # that nests it under "forecast" would pass against code reading the wrong
    # key and hide the exact bug this test exists to pin.
    monkeypatch.setattr(revenue_forecaster, "get_revenue_forecast", lambda *_: {
        "forecast": [{"day": "Monday", "predicted_revenue": 12000}],
        "weekly_pattern": [
            _weekly_row("Monday", 12000, 2.0, 4, 2),
            _weekly_row("Friday", 45000, 6.0, 12, 2),
        ],
    })
    answer = _answer_revenue(db_session, r.id, "Which days are slow?")
    assert answer["finding"].startswith("Monday is the slowest recorded day")
    assert "KES 120" in answer["finding"]          # cents -> KES, not KES 12,000
    assert answer["data"]["narrative_allowed"] is False
    assert "Friday" in answer["steps"][1]["action"]


def test_slow_days_ignores_weekdays_with_no_recorded_orders(monkeypatch, db_session, restaurant):
    """A weekday the restaurant never traded on is absent evidence, not a slow day.

    revenue_forecaster sets days_sampled = max(len(days_seen), 1), so an
    unobserved weekday still reports days_sampled == 1 with zero revenue.
    """
    from ai import revenue_forecaster
    _, r = restaurant
    monkeypatch.setattr(revenue_forecaster, "get_revenue_forecast", lambda *_: {
        "weekly_pattern": [
            _weekly_row("Tuesday", 0, 0.0, 0, 1),      # never traded
            _weekly_row("Monday", 12000, 2.0, 4, 2),
            _weekly_row("Friday", 45000, 6.0, 12, 2),
        ],
    })
    answer = _answer_revenue(db_session, r.id, "Which days are slow?")
    assert answer["finding"].startswith("Monday is the slowest recorded day")
    assert all("Tuesday" not in step["action"] for step in answer["steps"])
    assert [row["day"] for row in answer["data"]["weekly_pattern"]] == ["Monday", "Friday"]


def test_slow_days_without_any_recorded_orders_is_unavailable(monkeypatch, db_session, restaurant):
    """No traded weekday at all -> say so; never name a day off an empty window."""
    from ai import revenue_forecaster
    _, r = restaurant
    monkeypatch.setattr(revenue_forecaster, "get_revenue_forecast", lambda *_: {
        "weekly_pattern": [_weekly_row(d, 0, 0.0, 0, 1) for d in ("Monday", "Tuesday")],
    })
    answer = _answer_revenue(db_session, r.id, "Which days are slow?")
    assert answer["data"]["available"] is False
    assert answer["finding"] == "The data needed to answer this question is unavailable."


def test_what_did_i_sell_yesterday_is_that_days_sales_not_the_health_score(db_session):
    """A plain sales question names the day. It must not fall through to the health score."""
    from datetime import datetime, time, timedelta
    import models
    from owner import ask
    from routers.ai_ask import _answer_revenue
    from routers.overview import _EAT_OFFSET, _eat_now

    assert ask.classify("What did I sell yesterday?") == ("what", "revenue")
    tenant = models.Tenant(name="Sales Day")
    db_session.add(tenant)
    db_session.commit()
    restaurant_row = models.Restaurant(tenant_id=tenant.id, name="Sales Day", address="Nairobi")
    db_session.add(restaurant_row)
    db_session.commit()
    from time_utils import service_day
    now = _eat_now()
    # "Yesterday" is the day before the open service day (06:00 Nairobi rollover), not the calendar day.
    yesterday = service_day() - timedelta(days=1)
    yesterday_at = datetime.combine(yesterday, time(15, 0)) - _EAT_OFFSET
    # Today's sales window ends at the current minute, so the sale has to be earlier today.
    today_wall = now - timedelta(seconds=1)
    if today_wall.date() != now.date():
        today_wall = now
    today_at = today_wall - _EAT_OFFSET
    db_session.add(models.Order(
        restaurant_id=restaurant_row.id, total=25_000, is_paid=True, status=models.OrderStatus.SERVED, created_at=yesterday_at,
    ))
    db_session.add(models.Order(
        restaurant_id=restaurant_row.id, total=10_000, is_paid=True, status=models.OrderStatus.SERVED, created_at=today_at,
    ))
    db_session.commit()
    answer = _answer_revenue(db_session, restaurant_row.id, "What did I sell yesterday?")
    assert answer["finding"].startswith("Yesterday you sold")
    assert "KES 250" in answer["finding"]
    assert "1 paid" in answer["finding"]
    assert "health score" not in answer["finding"].lower()
    from time_utils import service_sales_window
    start, end, _service = service_sales_window()
    expected = 0
    if start <= yesterday_at < end:
        expected += 250
    if start <= today_at < end:
        expected += 100
    assert start <= today_at < end
    today = _answer_revenue(db_session, restaurant_row.id, "How are my sales today?")
    assert today["finding"].startswith("Revenue today is")
    assert f"KES {expected:,}" in today["finding"]


def _sales_pair(db_session, monkeypatch, frozen):
    """A restaurant and the two Ask answers for 'today', with the clock frozen."""
    import models
    from owner.answer_why import build
    from owner.states import OwnerContext
    from routers.ai_ask import _answer_revenue
    monkeypatch.setattr("time_utils.utcnow", lambda: frozen)
    monkeypatch.setattr("routers.overview.utcnow", lambda: frozen)
    monkeypatch.setattr("owner.states.utcnow", lambda: frozen)
    tenant = models.Tenant(name="Service Day")
    db_session.add(tenant)
    db_session.commit()
    restaurant_row = models.Restaurant(tenant_id=tenant.id, name="Service Day", address="Nairobi")
    db_session.add(restaurant_row)
    db_session.commit()
    user = models.User(tenant_id=tenant.id, email=f"svc-{restaurant_row.id}@example.com",
                       hashed_password="unused", role=models.Role.ADMIN)
    db_session.add(user)
    db_session.commit()
    return restaurant_row, lambda: (
        _answer_revenue(db_session, restaurant_row.id, "How were sales today?"),
        build(OwnerContext(db_session, user, restaurant_row), "Why were sales down today?"),
    )


def test_sales_today_and_why_today_agree_before_the_morning_rollover(db_session, monkeypatch):
    """01:30 Nairobi is still the previous service. Both answers count the same paid orders."""
    from datetime import datetime
    import models
    restaurant_row, answers = _sales_pair(db_session, monkeypatch, datetime(2026, 10, 23, 22, 30))
    def add(when, total, **extra):
        db_session.add(models.Order(
            restaurant_id=restaurant_row.id, total=total, is_paid=True,
            status=models.OrderStatus.SERVED, created_at=when, **extra,
        ))
    add(datetime(2026, 10, 23, 19, 0), 1_634_000)          # Friday 22:00 Nairobi
    add(datetime(2026, 10, 23, 21, 30), 20_000)            # Saturday 00:30 Nairobi, still this service
    add(datetime(2026, 10, 22, 12, 0), 999_900)            # Thursday afternoon, a different service
    db_session.add(models.Order(                          # unpaid, ignored by both
        restaurant_id=restaurant_row.id, total=50_000, is_paid=False,
        status=models.OrderStatus.READY, created_at=datetime(2026, 10, 23, 20, 0),
    ))
    db_session.add(models.Order(                          # cancelled, ignored by both
        restaurant_id=restaurant_row.id, total=40_000, is_paid=True,
        status=models.OrderStatus.CANCELLED, created_at=datetime(2026, 10, 23, 19, 30),
    ))
    db_session.commit()
    what, why = answers()
    assert "KES 16,540" in what["finding"]
    assert "2 paid" in what["finding"]
    sales = next(row for row in why["rows"] if row["key"] == "sales")
    assert sales["value"] == 16540


def test_sales_today_after_rollover_does_not_keep_the_previous_service(db_session, monkeypatch):
    from datetime import datetime
    import models
    restaurant_row, answers = _sales_pair(db_session, monkeypatch, datetime(2026, 10, 24, 12, 0))  # Saturday 15:00 Nairobi
    db_session.add(models.Order(
        restaurant_id=restaurant_row.id, total=1_634_000, is_paid=True,
        status=models.OrderStatus.SERVED, created_at=datetime(2026, 10, 23, 19, 0),  # Friday 22:00
    ))
    db_session.add(models.Order(
        restaurant_id=restaurant_row.id, total=10_000, is_paid=True,
        status=models.OrderStatus.SERVED, created_at=datetime(2026, 10, 24, 7, 0),  # Saturday 10:00
    ))
    db_session.commit()
    what, why = answers()
    assert "KES 100" in what["finding"]
    assert "KES 16,340" not in what["finding"]
    sales = next(row for row in why["rows"] if row["key"] == "sales")
    assert sales["value"] == 100


def test_ordinary_revenue_question_is_unaffected_by_the_slow_day_branch(monkeypatch, db_session, restaurant):
    from ai import revenue_forecaster
    _, r = restaurant
    monkeypatch.setattr(revenue_forecaster, "get_revenue_forecast", lambda *_: {
        "weekly_pattern": [_weekly_row("Monday", 12000, 2.0, 4, 2)],
    })
    answer = _answer_revenue(db_session, r.id, "How are my sales today?")
    assert answer["finding"].startswith("Revenue today is")


def test_slow_days_answer_runs_against_the_real_forecaster(db_session, restaurant):
    """End-to-end over the real get_revenue_forecast response.

    The monkeypatched cases above cannot catch a key that sits somewhere other
    than where the handler looks — that is exactly how "which days are slow?"
    shipped returning the unavailable card while its unit test asserted a day
    name. This one reads the genuine weekly_pattern off the fixture's orders.
    """
    _, r = restaurant
    weekdays = {"Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday"}
    answer = _answer_revenue(db_session, r.id, "Which days are slow?")
    assert answer["data"].get("available") is not False, answer["finding"]
    ranking = answer["data"]["weekly_pattern"]
    assert ranking, "the fixture trades every day; the pattern must not be empty"
    assert {row["day"] for row in ranking} <= weekdays
    assert all(row["total_orders"] > 0 for row in ranking)
    assert answer["finding"].startswith(ranking[0]["day"] + " is the slowest recorded day")
    assert answer["steps"] and answer["steps"][0]["action"].startswith(ranking[0]["day"])


def test_yesterday_before_the_morning_rollover_is_the_day_before_the_open_service(db_session, monkeypatch):
    """01:30 Saturday Nairobi: today is Friday's service, so yesterday is Thursday. The two must not overlap."""
    from datetime import datetime
    import models
    from owner.answer_why import build
    from owner.states import OwnerContext
    from routers.ai_ask import _answer_revenue
    restaurant_row, answers = _sales_pair(db_session, monkeypatch, datetime(2026, 10, 23, 22, 30))
    for when, total in ((datetime(2026, 10, 23, 19, 0), 1_634_000),   # Friday 22:00 Nairobi, the open service
                        (datetime(2026, 10, 22, 12, 0), 999_900)):    # Thursday 15:00 Nairobi
        db_session.add(models.Order(restaurant_id=restaurant_row.id, total=total, is_paid=True,
                                    status=models.OrderStatus.SERVED, created_at=when))
    db_session.commit()
    what = _answer_revenue(db_session, restaurant_row.id, "What did I sell yesterday?")
    assert "KES 9,999" in what["finding"] and "1 paid" in what["finding"], what["finding"]
    user = db_session.query(models.User).filter_by(tenant_id=restaurant_row.tenant_id).first()
    why = build(OwnerContext(db_session, user, restaurant_row), "Why were sales down yesterday?")
    assert why["day"] == "2026-10-22"
