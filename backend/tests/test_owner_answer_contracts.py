"""Owner answers must preserve the actual analytics contracts, not just HTTP 200."""
from tests.test_home_attention_intelligence import restaurant  # noqa: F401
from routers.ai_ask import _answer_menu, _answer_kitchen, _answer_staff, _answer_profit


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
