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


def test_slow_days_answer_is_specific_and_grounded(monkeypatch, db_session, restaurant):
    from ai import revenue_forecaster
    _, r = restaurant
    monkeypatch.setattr(revenue_forecaster, "get_revenue_forecast", lambda *_: {
        "weekly_pattern": [
            {"day": "Monday", "avg_revenue": 12000, "avg_orders": 2.0, "days_sampled": 2},
            {"day": "Friday", "avg_revenue": 45000, "avg_orders": 6.0, "days_sampled": 2},
        ]
    })
    answer = _answer_revenue(db_session, r.id, "Which days are slow?")
    assert answer["finding"].startswith("Monday is the slowest recorded day")
    assert answer["data"]["narrative_allowed"] is False
    assert "Friday" in answer["steps"][1]["action"]
