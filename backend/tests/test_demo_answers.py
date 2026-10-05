"""The prompted OS questions: each has its own answer, drawn from the scenario, filed under its own area."""
import json
import re
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

import demo_answers
import demo_scenario as demo
from tests.test_overview_scope import scoped_owner  # noqa: F401  (fixture used by demo_headers)
from tests.test_demo_showcase import demo_headers  # noqa: F401

DAY = date(2026, 9, 30)
QUESTIONS_FILE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "demoQuestions.ts"
needs_file = pytest.mark.skipif(not QUESTIONS_FILE.exists(), reason="frontend sources are not part of this checkout")


def screen_questions():
    """[(area slug, question)] exactly as the OS page lists them."""
    found, slug = [], None
    for line in QUESTIONS_FILE.read_text(encoding="utf-8").splitlines():
        match = re.match(r'\s+slug: "([^"]+)"', line)
        if match:
            slug = match.group(1)
            continue
        match = re.match(r'^\s+"([^"]+)",?\s*$', line)
        if match and slug:
            found.append((slug, match.group(1)))
    return found


@needs_file
def test_the_screen_and_the_backend_list_the_same_questions_under_the_same_areas():
    shown = screen_questions()
    assert shown
    on_screen = {demo_answers.normalise(question): slug for slug, question in shown}
    assert on_screen == demo_answers.known_questions()
    assert set(on_screen.values()) == set(demo.AREAS)       # every area has questions


@needs_file
def test_every_answer_is_plain_complete_and_different_from_the_others_in_its_area():
    by_area = {}
    for slug, question in screen_questions():
        text = demo_answers.answer_for(question, DAY)
        assert text and text == text.strip(), question
        assert "{" not in text and "}" not in text and "  " not in text, question
        by_area.setdefault(slug, []).append(text)
    for slug, texts in by_area.items():
        assert len(texts) == len(set(texts)), f"two questions in {slug} got the same answer"


def test_specific_figures_come_from_the_scenario():
    s = demo.scenario(DAY)
    sat = next(r for r in s["forecast"] if r["day"] == "Saturday")
    text = demo_answers.answer_for("How much should I expect to take on Saturday?", DAY)
    assert all(demo.money(sat[key]) in text for key in ("revenue", "low", "high"))
    assert f"About {sat['covers']} guests" in demo_answers.answer_for("How many guests should I expect on Saturday?", DAY)
    assert f"About {sat['people']} people" in demo_answers.answer_for("How many people do I need on Saturday?", DAY)
    assert f"About {sat['plates']} plates" in demo_answers.answer_for("How many plates will the kitchen prepare on Saturday?", DAY)
    chicken = next(x for x in s["stock"] if x["name"] == "Chicken")
    assert (chicken["runs_out_day"] or "Not within") in demo_answers.answer_for("When will the chicken run out?", DAY)
    beef = next(x for x in s["stock"] if x["name"] == "Beef")
    beef_text = demo_answers.answer_for("Will I have enough beef for the week?", DAY)
    assert f"{demo.qty(beef['order_qty'])} kg" in beef_text and beef["runs_out_day"] in beef_text
    assert demo.money(demo.UNMATCHED_KES) in demo_answers.answer_for("Why is KES 1,200 unmatched?", DAY)
    assert f"{demo.RETURNING_GUESTS} of {demo.ORDERS_TODAY} guests" in demo_answers.answer_for("How many of my guests are returning?", DAY)
    potential = sum(o["value"] for o in s["opportunities"])
    assert demo.money(potential) in demo_answers.answer_for("How much could I gain each day if everything works?", DAY)
    labor_pct = round(demo.LABOR_KES / s["history"][-1]["revenue"] * 100, 1)
    assert f"{labor_pct}%" in demo_answers.answer_for("What share of my sales goes on staff?", DAY)
    pilau = next(d for d in demo._dish_rows(s) if d["name"] == "Beef pilau")
    assert str(pilau["units"]) in demo_answers.answer_for("Should I raise the price of pilau?", DAY)


def test_answers_follow_the_scenario_when_a_figure_changes(monkeypatch):
    monkeypatch.setattr(demo, "WAITLIST", 9)
    monkeypatch.setattr(demo, "NO_SHOW_PCT", 10)
    assert "9 tables" in demo_answers.answer_for("What should I do about the waitlist?", DAY)
    assert "10%" in demo_answers.answer_for("What is my no-show rate?", DAY)


def test_a_typed_question_that_is_not_prompted_has_no_specific_answer():
    assert demo_answers.answer_for("Tell me a joke about beef", DAY) is None
    assert demo_answers.area_of("Tell me a joke about beef") is None
    assert demo_answers.answer_for("what AM I about to run out of", DAY)          # wording is matched, case and the ? are not


def test_a_prompted_question_gets_its_specific_answer_without_a_provider(client, demo_headers):
    with patch("ai.owner_narrative.narrate") as narrate:
        r = client.post("/api/v1/demo/chat", headers=demo_headers, json={"question": "When will the chicken run out?", "topic": "stock"})
        body = r.json()
        assert r.status_code == 200 and body["module"] == "stock"
        assert body["answer_text"] == demo_answers.answer_for("When will the chicken run out?")
        # Typed out in full with no topic, it still goes to its own area (keywords alone would say cash).
        typed = client.post("/api/v1/demo/chat", headers=demo_headers, json={"question": "Is the unmatched payment theft?"})
        assert typed.json()["module"] == "risk"
        assert narrate.call_count == 0


def test_the_ai_step_is_given_the_calculated_answer(client, demo_headers):
    from routers import demo as router
    router._cache.clear()
    router._ai_paused_until[0] = 0.0
    with patch("ai.owner_narrative.narrate", return_value="FINAL: Order the chicken early this week.") as narrate, \
            patch("ai.creative.enabled", return_value=True):
        r = client.post("/api/v1/demo/chat", headers=demo_headers,
                        json={"question": "When will the chicken run out?", "topic": "stock", "creative": True})
    assert r.status_code == 200
    assert narrate.call_count == 1
    source = json.loads(narrate.call_args.args[3][0]["content"])
    assert source["calculated_answer"] == demo_answers.answer_for("When will the chicken run out?")
    assert "calculated_answer" in narrate.call_args.args[4]
