"""
E3 — Grounding (docs/v2/SPEC.md §5): AI text never invents a number.
Pass: 100% of the numbers in narrated text appear in the payload; a planted wrong number is dropped.

Every place where words made by a language model reach an owner is driven here with a stubbed provider that PLANTS a wrong figure
(KES 987,654 and 37%) among sentences that cite real ones, and the planted figure must not survive. The words made by code (the Ask
LEVIII headlines, the report section headlines) are held to the same rule from the other side: every number in the sentence is
carried by a row, a driver, a column or an assumption of its own answer.

  surface                          what happens to the planted figure
  narrator (ai/reasoning)          redacted in place; the reply is flagged unverified
  report reply (routers/reports)   the whole optional paragraph is dropped; the deterministic report stands
  creative text (ai/creative)      its sentence is dropped, the rest stays; a text that is mostly invented is dropped whole
  OS chat, creative on, any answer type          its sentence is dropped
  OS chat, creative off, any answer type         the reply is dropped / its sentence is dropped  (general guidance was unchecked before E3)
  creative notes (report, Home)    its sentence is dropped
  owner sentences made by code     none can carry a figure its own answer does not show
"""
import json

import pytest

import models
from ai import creative, llm_client
from ai.reasoning import narrator
from ai.reasoning.grounding import verify
from owner.answers import ungrounded
from routers import ai_ask, reports
from tests.evals.test_e4_demo_scenarios import demo  # noqa: F401  (the planted-scenario restaurant, built once per module)
from tests.test_creative_layer import (  # noqa: F401
    RID, Provider, _fresh_creative_state, add_paid_order, provider, stub_os_modules, verify_source,
)
from tests.test_overview_scope import scoped_owner  # noqa: F401
from tests.test_source_connection_state import mirror_tables, source  # noqa: F401

PLANTED = ("987,654", "987654", "37%")


def leaked(text) -> list[str]:
    blob = json.dumps(text, ensure_ascii=False) if not isinstance(text, str) else text
    return [p for p in PLANTED if p in blob]


EVIDENCE = json.dumps({"revenue_kes": 500, "orders": 12, "average_order_kes": 42})
MIXED = ("Revenue reached KSh 500 across 12 orders. Sales will hit KES 987,654 by Friday. "
         "Food cost is already at 37%. Keep the grill warm.")


# ── narrator ─────────────────────────────────────────────────────────────────

PAYLOADS = {
    "profit": {"summary": {"gross_margin_pct": 62, "revenue": 500}, "channels": [{"name": "delivery"}]},
    "pricing": {"recommendations": [{"item": "Burger", "action": "REPRICE", "price": 650}]},
    "marketing": {"reachable_audience": 3, "lapsed_regulars": [{"name": "A"}]},
}


def _stub_narrator(monkeypatch, reply: dict):
    from types import SimpleNamespace
    narrator._cache.clear()
    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(llm_client, "chat_with_usage", lambda **kw: SimpleNamespace(
        text=json.dumps(reply), model="stub", usage=SimpleNamespace(input_tokens=1, output_tokens=1)))


@pytest.mark.parametrize("task", sorted(PAYLOADS))
def test_narrator_redacts_a_planted_figure_and_keeps_a_real_one(task, monkeypatch):
    real = {"profit": "62%", "pricing": "KES 650", "marketing": "3"}[task]
    _stub_narrator(monkeypatch, {
        "headline": f"Your margin is {real}, and it will reach KES 987,654.",
        "priorities": ["Food cost is already at 37%."], "actions": [{"action": "Raise it by 37%", "why": "demand", "impact": "KES 987,654 a year"}]})
    result = narrator.narrate(json.loads(json.dumps(PAYLOADS[task])), task)
    assert result["verified"] is False
    text = {k: result[k] for k in ("headline", "priorities", "actions")}          # the words the owner reads; `ungrounded_numbers` is the log of what was removed
    shown = json.dumps(text)
    assert leaked(text) == []
    assert "[unverified]" not in shown and "987,654" not in shown
    removed = " ".join(result["ungrounded_numbers"])
    assert "987,654" in removed and "37%" in removed


def test_narrator_leaves_a_grounded_reply_untouched(monkeypatch):
    _stub_narrator(monkeypatch, {"headline": "Gross margin is 62% on KES 500 of sales.", "priorities": [], "actions": []})
    result = narrator.narrate(json.loads(json.dumps(PAYLOADS["profit"])), "profit")
    assert result["verified"] is True and result["ungrounded_numbers"] == []
    assert result["headline"] == "Gross margin is 62% on KES 500 of sales."


# ── report reply, creative sentences ─────────────────────────────────────────

def test_the_optional_report_paragraph_is_dropped_whole_when_it_invents_a_figure():
    assert reports._grounded_reply(MIXED, EVIDENCE) is None
    assert reports._grounded_reply("Revenue reached KSh 500 across 12 orders. Keep the grill warm.", EVIDENCE) is not None


def test_creative_text_loses_the_planted_sentences_and_keeps_the_rest():
    text, dropped = creative.finish_text(MIXED, EVIDENCE)
    assert dropped == 2 and leaked(text) == []
    assert text == "Revenue reached KES 500 across 12 orders. Keep the grill warm."


def test_creative_text_that_is_mostly_invented_is_dropped_whole():
    text, dropped = creative.finish_text("Sales hit KES 987,654. Margin is 37%. Guests grew 41%. Keep the grill warm.", EVIDENCE)
    assert text is None and dropped == 3


@pytest.mark.parametrize("sentence,backed", [
    ("Revenue was KES 500.", True), ("Revenue was KSh 500.", True), ("Revenue was 500 shillings.", True),
    ("Revenue was KES 987,654.", False), ("Food cost was 37%.", False), ("There were 12 orders.", True),
    ("There were 1,200 orders.", False), ("Sales were 4.2% up.", False), ("Keep the grill warm.", True),
])
def test_the_verifier_agrees_with_a_hand_checked_table(sentence, backed):
    assert verify({"headline": sentence}, EVIDENCE)["verified"] is backed


# ── OS chat: both modes, both kinds of answer ────────────────────────────────

ASK = "/api/v1/ai/chat"
GENERAL = {"question": "Help me reduce food waste.", "answer_mode": "general"}


def _chat(client, headers, payload):
    r = client.post(ASK, headers=headers, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_os_chat_general_guidance_drops_a_planted_figure_with_the_creative_layer_on(client, scoped_owner, provider):
    _, headers = scoped_owner
    provider("Record waste every night. Cut it by 37% in a month. Talk to your team first.")
    body = _chat(client, headers, GENERAL)
    assert leaked(body) == [] and body["answer_text"] == "Record waste every night. Talk to your team first."


def test_os_chat_general_guidance_drops_a_planted_figure_with_the_creative_layer_off(client, scoped_owner, provider):
    """The gap E3 found: with the creative layer off, general guidance reached the owner unchecked (only restaurant analysis was grounded)."""
    _, headers = scoped_owner
    provider("Record waste every night. Cut it by 37% in a month. Talk to your team first.", creative_on=False)
    body = _chat(client, headers, GENERAL)
    assert body["llm_used"] is True and leaked(body) == []
    assert body["answer_text"] == "Record waste every night. Talk to your team first."


def test_os_chat_general_guidance_keeps_the_owners_own_figures_with_the_creative_layer_off(client, scoped_owner, provider):
    _, headers = scoped_owner
    provider("Waste of KSh 80,000 is worth fixing. Start with the bin count.", creative_on=False)
    body = _chat(client, headers, {"question": "We lose about KSh 80,000 a month to waste. Help me reduce it.", "answer_mode": "general"})
    assert "KES 80,000" in body["answer_text"] and body["llm_used"] is True


def test_os_chat_fully_invented_general_reply_falls_back_with_the_creative_layer_off(client, scoped_owner, provider):
    _, headers = scoped_owner
    provider("You will earn KSh 987,654. Profit will grow 37%. Expect 4,000 guests.", creative_on=False)
    body = _chat(client, headers, GENERAL)
    assert leaked(body) == [] and body["llm_used"] is False


@pytest.mark.parametrize("creative_on", [True, False])
def test_os_chat_restaurant_analysis_drops_a_planted_figure_in_both_modes(client, db_session, scoped_owner, provider, source, monkeypatch, creative_on):
    _, headers = scoped_owner
    provider("Revenue is KSh 500. Sales will reach KES 987,654. Keep the grill warm.", creative_on=creative_on)
    verify_source(db_session, source)
    add_paid_order(db_session)
    stub_os_modules(monkeypatch)
    body = _chat(client, headers, {"question": "How are my sales today?"})
    assert leaked(body) == []
    if creative_on:
        assert body["answer_text"] == "Revenue is KES 500. Keep the grill warm."
    else:
        assert "987" not in json.dumps(body)               # a restaurant-analysis reply that invents a figure is dropped whole


# ── creative notes on Home and in reports ────────────────────────────────────

@pytest.mark.parametrize("url", ["/api/v1/ai/creative/home", "/api/v1/reports/daily/creative"])
def test_creative_notes_carry_no_planted_figure(client, db_session, scoped_owner, provider, url):
    _, headers = scoped_owner
    provider("Keep the grill warm today. Margin will reach 37%. Sales could touch KES 987,654.")
    add_paid_order(db_session)
    body = client.get(url, headers=headers).json()
    assert leaked(body) == []


# ── words made by code ───────────────────────────────────────────────────────

FORM_QUESTIONS = (
    "What if I raise the price of Chips to 350?", "What should I do to make more money?", "How can I find KES 20,000 more a month?",
    "Compare my branches", "This week vs last week", "Why were sales down last Wednesday?",
)


def test_every_ask_headline_on_the_demo_restaurant_is_backed_by_its_own_rows(demo):  # noqa: F811
    """The seven areas answered from Home's blocks, and the four other forms: no figure in a sentence that its own rows do not carry."""
    from owner import ask
    ctx = demo["ctx"]["A"]
    from owner import answer_what
    # The nine old handlers' sentences (S5.1 left them as they were) state their figures in the sentence itself, copied by code from the
    # engine's values; there are no rows to back them, so what E3 holds them to is the language-model text laid over them (below).
    topics = [t for t in ask.what_topics() if t not in answer_what.legacy_topics()]
    cases = [("How is it going?", topic) for topic in topics] + [(q, None) for q in FORM_QUESTIONS]
    for question, topic in cases:
        answer = ask.ask(ctx, question, topic=topic)
        stray = ungrounded(answer)
        assert stray == [], f"{topic or question!r} states {stray} that no row carries: {answer['headline']!r}"
    assert len(cases) >= 13


@pytest.mark.parametrize("period", ["daily", "weekly", "monthly", "yearly"])
def test_every_report_section_headline_on_the_demo_restaurant_is_backed_by_its_rows(demo, period):  # noqa: F811
    from owner.reports import compose_report
    report = compose_report(demo["ctx"]["A"], period)
    checked = 0
    for section in report["sections"]:
        if section.get("headline"):
            stray = ungrounded(section)
            assert stray == [], f"{period}.{section['key']} states {stray} that no row carries: {section['headline']!r}"
            checked += 1
    # The sweep must not be vacuous, whatever the hour. The engines read the real clock, and a daily report asked before the restaurant has taken
    # its first sale (07:00 in Nairobi) has nothing to say about today's sales, best sellers or drawer: those say "no data" and carry no headline,
    # which is right. Then only the two sections that do not depend on today's sales speak (things to check, stock today).
    sales = next((s for s in report["sections"] if s["key"] == "sales"), None)
    quiet_day = period == "daily" and (sales is None or sales.get("state") == "no_data")
    assert checked >= (2 if quiet_day else 3), f"{period}: only {checked} section headlines were checked"


def test_the_alert_digest_is_backed_by_its_rows(demo):  # noqa: F811
    from ai import alert_levels
    ctx = demo["ctx"]["A"]
    digest = alert_levels.build_digest(demo["db"], ctx.user)
    if digest is not None:                                 # a demo with no sales yet today may have nothing to say
        assert ungrounded(digest) == []
