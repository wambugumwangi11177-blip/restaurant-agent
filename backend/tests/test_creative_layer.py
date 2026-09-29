"""Creative (stochastic) LLM layer — ADR 0007.

Every test drives the real routers and captures what would be sent to the
provider (`llm_client.chat_with_usage`), so the assertions are about the outbound
payload, the persisted usage and the served text — not about mocks being called.
"""
import importlib.util
import json
import threading
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

import auth
import models
import observer_mode
from ai import creative, llm_client, owner_narrative, spend_cap
from integration.models import ReconcileRun
from routers import ai_ask, overview, reports
from tests.test_overview_scope import scoped_owner  # noqa: F401
from tests.test_source_connection_state import _event, mirror_tables, source  # noqa: F401
from time_utils import utcnow

HOME = "/api/v1/ai/creative/home"
RID = 202  # scoped_owner's selected restaurant


@pytest.fixture(autouse=True)
def _fresh_creative_state():
    creative.reset_runtime_state()
    yield
    creative.reset_runtime_state()


class Provider:
    """Captures every outbound call and replays scripted replies."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []  # (messages, kwargs)

    def __call__(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply, model="test-model",
                               usage=SimpleNamespace(input_tokens=120, output_tokens=60))

    @property
    def outbound(self):
        return json.dumps(self.calls, ensure_ascii=False)


@pytest.fixture
def provider(monkeypatch):
    def install(*replies, creative_on=True):
        stub = Provider(replies or ["A calm day. Revenue is KSh 500."])
        monkeypatch.setattr(llm_client, "is_available", lambda: True)
        monkeypatch.setattr(llm_client, "model_for_tier", lambda tier: f"model-for-{tier}")
        monkeypatch.setattr(llm_client, "chat_with_usage", stub)
        if creative_on:
            monkeypatch.setenv("FEATURE_CREATIVE_LAYER", "true")
        return stub
    return install


def add_paid_order(db, total_cents=50000, rid=RID):
    db.add(models.Order(restaurant_id=rid, is_paid=True, total=total_cents, status=models.OrderStatus.SERVED))
    db.commit()


def verify_source(db, source):
    db.add(_event(source.id, utcnow(), "INV-1"))
    db.add(ReconcileRun(source_system_id=source.id, entity="sale", source_count=1, mirror_count=1,
                        source_checksum="a", mirror_checksum="a", status="clean"))
    db.commit()


# ── Grounding ────────────────────────────────────────────────────────────────

EVIDENCE = json.dumps({"revenue_kes": 500, "orders": 12, "average_order_kes": 42})


def test_invented_figure_drops_only_its_sentence():
    text, dropped = creative.keep_grounded_sentences(
        "Revenue reached KSh 500. Try a 25% discount. Keep the grill warm.", EVIDENCE)
    assert text == "Revenue reached KSh 500. Keep the grill warm."
    assert dropped == 1


def test_mostly_invented_text_is_discarded():
    text, dropped = creative.keep_grounded_sentences(
        "Revenue hit KSh 9,999. Orders reached 77. Sales rose 31%. Keep the grill warm.", EVIDENCE)
    assert text is None
    assert dropped == 3


def test_half_dropped_is_kept_more_than_half_is_not():
    two_of_four, _ = creative.keep_grounded_sentences("KSh 500 today. KSh 777 more. Warm day. Fresh air.", EVIDENCE)
    assert two_of_four is not None
    one_of_three, _ = creative.keep_grounded_sentences("KSh 777 more. KSh 888 less. Warm day.", EVIDENCE)
    assert one_of_three is None


def test_bullets_and_lines_survive_filtering():
    text, dropped = creative.keep_grounded_sentences(
        "- Revenue reached KSh 500.\n- Try a 25% discount.\n\n- Keep the grill warm.", EVIDENCE)
    assert text == "- Revenue reached KSh 500.\n\n- Keep the grill warm."
    assert dropped == 1


def test_empty_and_overlong_text():
    assert creative.keep_grounded_sentences("   ", EVIDENCE) == (None, 0)
    text, _ = creative.keep_grounded_sentences("Keep the grill warm. " * 90, EVIDENCE)
    assert len(text) <= creative.MAX_TEXT_CHARS and text.endswith(".")


def test_owner_words_count_as_grounding():
    source = EVIDENCE + "\nOur rent is KSh 80,000 a month"
    text, dropped = creative.keep_grounded_sentences("You said KSh 80,000 is the rent.", source)
    assert text == "You said KSh 80,000 is the rent." and dropped == 0


def test_reasoning_blocks_are_stripped():
    assert owner_narrative.strip_reasoning_leak("<think>plan the answer</think>Warm day.") == "Warm day."
    assert owner_narrative.strip_reasoning_leak("<think>cut off mid thought") == ""
    assert owner_narrative.strip_reasoning_leak("scratch work</think>The real text.") == "The real text."


# ── Provider boundary ────────────────────────────────────────────────────────

def test_narrate_defaults_are_deterministic_and_flag_off_changes_nothing(client, db_session, scoped_owner, provider):
    _, headers = scoped_owner
    stub = provider("Revenue is KSh 500.", creative_on=False)
    add_paid_order(db_session)
    body = client.get("/api/v1/reports/daily", headers=headers).json()
    assert body["llm_used"] is True
    (_, kwargs), = stub.calls
    assert kwargs["temperature"] == 0 and kwargs["tier"] == "medium"
    assert db_session.query(models.TokenUsage).one().prompt_version == "owner-report-v2"
    # The layer is off: its endpoints answer without any provider call.
    home = client.get(HOME, headers=headers).json()
    assert home["text"] is None and home["reason"] == "disabled"
    assert client.get("/api/v1/reports/daily/creative", headers=headers).json()["reason"] == "disabled"
    assert len(stub.calls) == 1


def test_creative_tier_resolves_and_defaults_to_the_medium_model():
    for provider_name, tiers in llm_client._MODEL_TIERS.items():
        assert tiers[llm_client.TIER_CREATIVE] == tiers[llm_client.TIER_MEDIUM], provider_name
    assert llm_client.TIER_CREATIVE in llm_client._MODEL_TIERS["openrouter"]


def test_disabled_kill_switch_silences_the_layer(client, scoped_owner, provider, monkeypatch):
    _, headers = scoped_owner
    stub = provider()
    monkeypatch.setenv("FEATURE_AI_NARRATION", "false")
    body = client.get(HOME, headers=headers).json()
    assert body["text"] is None and body["reason"] == "disabled"
    assert not stub.calls


def test_ai_narration_off_stops_report_and_os_llm_calls_too(client, db_session, scoped_owner, provider, monkeypatch):
    _, headers = scoped_owner
    stub = provider(creative_on=False)
    monkeypatch.setenv("FEATURE_AI_NARRATION", "false")
    add_paid_order(db_session)
    assert client.get("/api/v1/reports/daily", headers=headers).json()["llm_used"] is False
    monkeypatch.setitem(ai_ask._HANDLERS, "revenue", lambda *_: ai_ask._unavailable_card("revenue"))
    chat = client.post("/api/v1/ai/chat", headers=headers, json={"question": "How are sales today?"})
    assert chat.status_code == 200 and chat.json()["llm_used"] is False
    assert not stub.calls


# ── Home ─────────────────────────────────────────────────────────────────────

def test_home_unverified_source_tells_the_system_story_with_no_restaurant_figures(
        client, db_session, scoped_owner, provider):
    _, headers = scoped_owner
    stub = provider("Your Restaurant OS keeps Home, the OS and Reports together.")
    add_paid_order(db_session, total_cents=98765)  # KSh 987.65 — must never leave the server
    response = client.get(HOME, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["mode"], body["period"], body["surface"]) == ("system_story", "any", "home")
    assert body["text"].startswith("Your Restaurant OS") and body["llm_used"] is True and body["stale"] is False
    (messages, kwargs), = stub.calls
    assert kwargs["temperature"] == creative.TEMPERATURE > 0
    assert kwargs["tier"] == "creative"
    outbound = stub.outbound
    for private in ("987", "98765", "Selected stock", "Sibling", "Foreign"):
        assert private not in outbound
    assert "planned, not available" in outbound
    assert db_session.query(models.TokenUsage).one().prompt_version == "creative-system_story-v1"


def test_home_receiving_but_unreconciled_is_still_the_system_story(client, db_session, scoped_owner, provider, source):
    _, headers = scoped_owner
    stub = provider("The software is ready for your data.")
    db_session.add(_event(source.id, utcnow(), "INV-1"))
    db_session.commit()
    add_paid_order(db_session)
    body = client.get(HOME, headers=headers).json()
    assert body["mode"] == "system_story"
    assert "clean reconciliation" in stub.outbound


def test_home_verified_source_tells_todays_story_from_recorded_figures(
        client, db_session, scoped_owner, provider, source):
    _, headers = scoped_owner
    stub = provider("Revenue is KSh 500 today. Try a lunch special.")
    verify_source(db_session, source)
    add_paid_order(db_session, total_cents=50000)
    response = client.get(f"{HOME}?period=today", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["mode"], body["period"]) == ("today_story", "today")
    assert body["text"] == "Revenue is KSh 500 today. Try a lunch special."
    (messages, _), = stub.calls
    evidence = messages[0]["content"]
    assert '"revenue_kes": 500' in evidence and '"paid_orders": 1' in evidence
    assert "not_available" in evidence
    row = db_session.query(models.CreativeTake).one()
    assert (row.restaurant_id, row.mode, row.prompt_version) == (RID, "today_story", "creative-today_story-v1")
    assert len(row.evidence_hash) == 64 and row.llm_model == "model-for-creative"


def test_home_evidence_is_scoped_to_the_selected_restaurant(client, db_session, scoped_owner, provider, source):
    _, headers = scoped_owner
    stub = provider("Revenue is KSh 500 today.")
    verify_source(db_session, source)
    add_paid_order(db_session, total_cents=50000, rid=RID)
    add_paid_order(db_session, total_cents=777700, rid=203)  # sibling restaurant, same tenant
    client.get(HOME, headers=headers)
    assert "7777" not in stub.outbound and "Sibling" not in stub.outbound


def test_home_with_no_orders_says_records_do_not_prove_a_quiet_day(client, db_session, scoped_owner, provider, source):
    _, headers = scoped_owner
    stub = provider("Nothing is recorded yet today.")
    verify_source(db_session, source)
    client.get(HOME, headers=headers)
    assert "does not show that no guests came" in stub.outbound


def test_home_rejects_an_unknown_period(client, scoped_owner):
    _, headers = scoped_owner
    assert client.get(f"{HOME}?period=decade", headers=headers).status_code == 422


def test_yesterdays_story_is_never_served_as_todays(client, db_session, scoped_owner, provider, source):
    _, headers = scoped_owner
    stub = provider("Revenue is KSh 500 today.")
    verify_source(db_session, source)
    add_paid_order(db_session)
    day_start = overview._eat_range("today")[0]
    db_session.add(models.CreativeTake(
        restaurant_id=RID, surface="home", period="today", mode="today_story",
        text="Yesterday was lovely.", evidence_hash="0" * 64, created_at=day_start - timedelta(minutes=10)))
    db_session.commit()
    body = client.get(f"{HOME}?period=today", headers=headers).json()
    assert body["text"] == "Revenue is KSh 500 today."
    assert len(stub.calls) == 1
    assert db_session.query(models.CreativeTake).count() == 2  # yesterday's row stays as history


# ── Caching and failure behaviour ────────────────────────────────────────────

def test_second_load_is_served_from_the_database(client, db_session, scoped_owner, provider):
    _, headers = scoped_owner
    stub = provider("First version.")
    first = client.get(HOME, headers=headers).json()
    second = client.get(HOME, headers=headers).json()
    assert first["text"] == second["text"] == "First version."
    assert first["generated_at"] == second["generated_at"]
    assert len(stub.calls) == 1


def test_evidence_is_only_built_when_a_provider_call_is_made(db_session, scoped_owner, provider):
    user, _ = scoped_owner
    provider("Warm day.")
    built = []

    def evidence():
        built.append(1)
        return {"date": "today"}

    for _ in range(3):
        creative.take(db_session, user, RID, surface="home", period="any", mode="system_story", evidence=evidence)
    assert len(built) == 1


def test_stale_text_is_served_and_flagged_and_refresh_replaces_it(client, db_session, scoped_owner, provider, monkeypatch):
    _, headers = scoped_owner
    stub = provider("First version.", "Second version.")
    client.get(HOME, headers=headers)
    monkeypatch.setattr(creative, "SYSTEM_STORY_TTL_SECONDS", 0)
    stale = client.get(HOME, headers=headers).json()
    assert stale["text"] == "First version." and stale["stale"] is True and len(stub.calls) == 1
    # A refresh straight after a write is debounced: the take just written is returned.
    debounced = client.get(f"{HOME}?refresh=1", headers=headers).json()
    assert debounced["text"] == "First version." and len(stub.calls) == 1
    monkeypatch.setattr(creative, "MIN_REFRESH_SECONDS", 0)
    refreshed = client.get(f"{HOME}?refresh=1", headers=headers).json()
    assert refreshed["text"] == "Second version."
    assert db_session.query(models.CreativeTake).count() == 2


def test_failed_refresh_keeps_the_last_good_text(client, db_session, scoped_owner, provider, monkeypatch):
    _, headers = scoped_owner
    stub = provider("First version.", RuntimeError("provider down: secret detail"))
    client.get(HOME, headers=headers)
    monkeypatch.setattr(creative, "MIN_REFRESH_SECONDS", 0)
    body = client.get(f"{HOME}?refresh=1", headers=headers)
    assert body.status_code == 200
    data = body.json()
    assert data["text"] == "First version."
    assert data["stale"] is True and data["refresh_failed"] is True and data["reason"] == "provider_error"
    assert "secret detail" not in body.text
    assert db_session.query(models.CreativeTake).count() == 1


def test_failure_cooldown_stops_hammering_a_broken_provider(client, scoped_owner, provider, monkeypatch):
    _, headers = scoped_owner
    stub = provider(RuntimeError("down"))
    for _ in range(4):
        body = client.get(HOME, headers=headers).json()
        assert body["text"] is None and body["reason"] == "provider_error"
    assert len(stub.calls) == 1
    creative.reset_runtime_state()
    client.get(HOME, headers=headers)
    assert len(stub.calls) == 2


def test_budget_reached_is_a_soft_failure_not_a_429(client, scoped_owner, provider, monkeypatch):
    _, headers = scoped_owner
    stub = provider()
    monkeypatch.setattr(spend_cap, "DAILY_LLM_SPEND_CAP_USD", 0)
    response = client.get(HOME, headers=headers)
    assert response.status_code == 200
    assert response.json()["text"] is None and response.json()["reason"] == "budget_reached"
    assert not stub.calls


def test_ungrounded_output_is_discarded_but_the_spend_is_metered(client, db_session, scoped_owner, provider):
    _, headers = scoped_owner
    provider("Sales hit KSh 9,999. Orders reached 77. Growth was 31%.")
    body = client.get(HOME, headers=headers).json()
    assert body["text"] is None and body["reason"] == "ungrounded"
    assert db_session.query(models.CreativeTake).count() == 0
    assert db_session.query(models.TokenUsage).count() == 1


def test_leaked_reasoning_never_reaches_the_owner(client, scoped_owner, provider):
    _, headers = scoped_owner
    provider("<think>We need to write about the software.</think>The OS is ready when you are.")
    assert client.get(HOME, headers=headers).json()["text"] == "The OS is ready when you are."


def test_only_the_newest_fifty_takes_per_key_are_kept(db_session, scoped_owner, provider):
    user, _ = scoped_owner
    provider("Fresh take.")
    for i in range(60):
        db_session.add(models.CreativeTake(
            restaurant_id=RID, surface="home", period="any", mode="system_story", text=f"old {i}",
            evidence_hash="0" * 64, created_at=utcnow() - timedelta(days=2, minutes=i)))
    db_session.commit()
    creative.take(db_session, user, RID, surface="home", period="any", mode="system_story",
                  evidence={"x": 1}, refresh=True)
    rows = db_session.query(models.CreativeTake).order_by(models.CreativeTake.created_at.desc()).all()
    assert len(rows) == 50 and rows[0].text == "Fresh take."


def test_concurrent_cold_loads_spend_one_provider_call(db_session, scoped_owner, provider, monkeypatch):
    user, _ = scoped_owner
    stub = provider("One take for everyone.")

    def slow(messages, **kwargs):
        time.sleep(0.3)
        return stub(messages, **kwargs)

    monkeypatch.setattr(llm_client, "chat_with_usage", slow)
    # The dedupe must not depend on the debounce window: identity decides it.
    monkeypatch.setattr(creative, "MIN_REFRESH_SECONDS", 0)
    import database
    results = []

    def load():
        session = database.SessionLocal()
        try:
            me = session.get(models.User, user.id)
            results.append(creative.take(session, me, RID, surface="home", period="any",
                                         mode="system_story", evidence={"x": 1}))
        finally:
            session.close()

    threads = [threading.Thread(target=load) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(stub.calls) == 1
    assert {r["text"] for r in results} == {"One take for everyone."}


def test_concurrent_refreshes_spend_one_provider_call(db_session, scoped_owner, provider, monkeypatch):
    user, _ = scoped_owner
    stub = provider("First take.", "Refreshed once.")
    creative.take(db_session, user, RID, surface="home", period="any", mode="system_story", evidence={"x": 1})
    monkeypatch.setattr(creative, "MIN_REFRESH_SECONDS", 0)

    def slow(messages, **kwargs):
        time.sleep(0.3)
        return stub(messages, **kwargs)

    monkeypatch.setattr(llm_client, "chat_with_usage", slow)
    import database
    results = []

    def refresh():
        session = database.SessionLocal()
        try:
            me = session.get(models.User, user.id)
            results.append(creative.take(session, me, RID, surface="home", period="any",
                                         mode="system_story", evidence={"x": 1}, refresh=True))
        finally:
            session.close()

    threads = [threading.Thread(target=refresh) for _ in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(stub.calls) == 2  # the first take + exactly one refresh
    assert {r["text"] for r in results} == {"Refreshed once."}


def test_takes_are_never_served_across_restaurants(client, db_session, scoped_owner, provider):
    _, headers_a = scoped_owner
    stub = provider("Take for the selected restaurant.", "Take for the foreign restaurant.")
    other = models.User(tenant_id=202, active_restaurant_id=303, email="foreign-owner@example.com",
                        hashed_password="unused", role=models.Role.ADMIN)
    db_session.add(other)
    db_session.commit()
    headers_b = {"Authorization": f"Bearer {auth.create_access_token({'sub': other.email})}"}
    a = client.get(HOME, headers=headers_a).json()
    b = client.get(HOME, headers=headers_b).json()
    assert a["text"] == "Take for the selected restaurant."
    assert b["text"] == "Take for the foreign restaurant."
    assert len(stub.calls) == 2
    assert {r.restaurant_id for r in db_session.query(models.CreativeTake)} == {RID, 303}


def test_creative_endpoints_require_an_owner_session(client):
    assert client.get(HOME).status_code in (401, 403)
    assert client.get("/api/v1/reports/daily/creative").status_code in (401, 403)


def test_observer_mode_blocks_the_creative_endpoints():
    assert observer_mode.is_blocked_request("GET", "/api/v1/ai/creative/home")
    assert observer_mode.is_blocked_request("GET", "/api/v1/reports/daily/creative")


# ── Reports ──────────────────────────────────────────────────────────────────

def test_report_with_no_orders_makes_no_provider_call(client, scoped_owner, provider):
    _, headers = scoped_owner
    stub = provider()
    body = client.get("/api/v1/reports/daily/creative", headers=headers).json()
    assert body["text"] is None and body["reason"] == "no_data" and body["mode"] == "report_take"
    assert not stub.calls


def test_report_take_carries_report_figures_and_related_findings(client, db_session, scoped_owner, provider, monkeypatch):
    _, headers = scoped_owner
    stub = provider("My read: Friday could carry a set menu. Try this: offer it for one week.")
    add_paid_order(db_session, total_cents=50000)
    db_session.add(models.MenuItem(restaurant_id=RID, name="Nyama choma", price=90000, category="mains"))
    db_session.commit()
    monkeypatch.setitem(ai_ask._HANDLERS, "menu", lambda *_: {
        "finding": "Menu mix: 1 star item(s) driving profit", "why": "Popularity vs margin.", "impact": "Avg food cost 31%",
        "recommendation": "Promote Nyama choma.", "module": "menu", "steps": [], "data": {}})
    monkeypatch.setitem(ai_ask._HANDLERS, "profit", lambda *_: ai_ask._unavailable_card("profit"))
    body = client.get("/api/v1/reports/daily/creative", headers=headers)
    assert body.status_code == 200, body.text
    assert body.json()["mode"] == "report_take" and body.json()["text"].startswith("My read:")
    (messages, kwargs), = stub.calls
    evidence = json.loads(messages[0]["content"].split("\n", 1)[1])
    assert evidence["report"]["revenue_kes"] == 500 and evidence["report"]["paid_orders"] == 1
    assert "30-day analysis window" in evidence["related"]["basis"]
    assert list(evidence["related"]["findings"]) == ["menu"]  # profit said "unavailable": contributes nothing
    assert "recorded data only" in evidence["data_status"]
    assert kwargs["temperature"] == creative.TEMPERATURE
    assert body.json()["period"] == "daily"


def test_report_take_rejects_an_unknown_period(client, scoped_owner):
    _, headers = scoped_owner
    assert client.get("/api/v1/reports/hourly/creative", headers=headers).status_code == 422


# ── OS ───────────────────────────────────────────────────────────────────────

def stub_os_modules(monkeypatch):
    def card(module, finding):
        return lambda *_: {"finding": finding, "why": "Recorded sales.", "impact": "Not quantified",
                           "recommendation": f"Review {module}.", "module": module,
                           "steps": [{"action": f"Look at {module}"}], "data": {}}
    monkeypatch.setitem(ai_ask._HANDLERS, "revenue", card("revenue", "Revenue is KSh 500 across 1 paid orders."))
    monkeypatch.setitem(ai_ask._HANDLERS, "menu", card("menu", "Menu mix: 2 star item(s) driving profit"))
    monkeypatch.setitem(ai_ask._HANDLERS, "bookings", lambda *_: pytest.fail("no reservations exist: must be skipped"))


def test_os_creative_makes_one_call_over_several_modules(client, db_session, scoped_owner, provider, source, monkeypatch):
    _, headers = scoped_owner
    stub = provider("You mentioned KSh 80,000 in rent. Revenue is KSh 500. Try a 25% discount. Keep the grill warm.")
    verify_source(db_session, source)
    add_paid_order(db_session)
    db_session.add(models.MenuItem(restaurant_id=RID, name="Nyama choma", price=90000, category="mains"))
    db_session.commit()
    stub_os_modules(monkeypatch)
    response = client.post("/api/v1/ai/chat", headers=headers, json={
        "question": "Our rent is KSh 80,000. How are my sales today and which dishes sell best?"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(stub.calls) == 1
    (messages, kwargs), = stub.calls
    assert kwargs["temperature"] == creative.TEMPERATURE and kwargs["tier"] == "creative"
    evidence = next(m["content"] for m in messages if m["content"].startswith("Verified evidence"))
    payload = json.loads(evidence.split("\n", 1)[1])
    assert set(payload) == {"primary", "related"}
    assert list(payload["related"]) == ["menu"]  # bookings has no records: skipped, never guessed
    assert body["creative"] is True and body["llm_used"] is True
    assert body["consulted_modules"] == ["revenue", "menu"]
    # Owner-supplied and evidence figures survive; the invented 25% does not.
    assert body["answer_text"] == "You mentioned KSh 80,000 in rent. Revenue is KSh 500. Keep the grill warm."
    assert body["dropped_sentences"] == 1
    assert db_session.query(models.TokenUsage).one().prompt_version == "owner-os-creative-v1"


def test_os_creative_grounds_general_guidance_too(client, scoped_owner, provider):
    _, headers = scoped_owner
    provider("Start by recording waste each night. Cut it by 40% in a month. Talk to your team first.")
    body = client.post("/api/v1/ai/chat", headers=headers, json={
        "question": "Help me reduce food waste.", "answer_mode": "general"}).json()
    assert body["answer_type"] == "general_guidance" and body["creative"] is True
    assert body["answer_text"] == "Start by recording waste each night. Talk to your team first."
    assert body["consulted_modules"] == []


def test_os_creative_fully_invented_reply_falls_back_to_the_deterministic_text(client, scoped_owner, provider):
    _, headers = scoped_owner
    provider("You will earn KSh 9,999,999. Profit will grow 300%. Expect 4,000 guests.")
    body = client.post("/api/v1/ai/chat", headers=headers, json={
        "question": "Help me reduce food waste.", "answer_mode": "general"}).json()
    assert body["llm_used"] is False and body["creative"] is False
    assert body["answer_text"].startswith("I can help work through this as general guidance")


def test_os_creative_keeps_planned_features_deterministic(client, scoped_owner, provider):
    _, headers = scoped_owner
    stub = provider()
    body = client.post("/api/v1/ai/chat", headers=headers, json={
        "question": "Which supplier is cheapest?", "answer_mode": "analysis"}).json()
    assert body["answer_type"] == "planned_feature" and body["llm_used"] is False
    assert not stub.calls


def test_os_flag_off_response_shape_is_unchanged(client, scoped_owner, provider):
    _, headers = scoped_owner
    provider("Start by recording waste each night.", creative_on=False)
    body = client.post("/api/v1/ai/chat", headers=headers, json={
        "question": "Help me reduce food waste.", "answer_mode": "general"}).json()
    assert body["llm_used"] is True
    assert "creative" not in body and "consulted_modules" not in body


def test_orchestrate_orders_primary_then_matches_then_companions_and_caps_at_three():
    assert ai_ask._orchestrate("How are my sales today?", "revenue") == ["revenue", "menu", "bookings"]
    assert ai_ask._orchestrate("Which dishes make the most money and what is my profit?", "menu") == [
        "menu", "profit", "pricing"]
    assert ai_ask._orchestrate("Anything I should know?", "ops") == ["ops", "revenue", "stock"]
    for question, primary in (("stock and bookings and staff and menu and profit?", "stock"),
                              ("How are my sales?", "revenue")):
        modules = ai_ask._orchestrate(question, primary)
        assert modules[0] == primary and len(modules) == len(set(modules)) <= 3


def test_gather_evidence_isolates_a_failing_module(db_session, scoped_owner, monkeypatch):
    add_paid_order(db_session)
    monkeypatch.setitem(ai_ask._HANDLERS, "revenue", lambda *_: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setitem(ai_ask._HANDLERS, "profit", lambda *_: {
        "finding": "f", "why": "w", "impact": "i", "recommendation": "r", "steps": [{"a": 1}] * 5, "data": {}})
    found = ai_ask._gather_evidence(db_session, RID, ["revenue", "profit"], "q")
    assert list(found) == ["profit"] and len(found["profit"]["steps"]) == 3


# ── Migration ────────────────────────────────────────────────────────────────

def test_creative_takes_migration_is_safe_after_model_create_all():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(engine)
    path = Path(__file__).parents[1] / "alembic/versions/050_add_creative_takes.py"
    spec = importlib.util.spec_from_file_location("creative_takes_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert (migration.revision, migration.down_revision) == ("050_creative_takes", "049_owner_os_workspace")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert "creative_takes" in inspect(connection).get_table_names()
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert "creative_takes" not in inspect(connection).get_table_names()
    engine.dispose()


def test_creative_takes_migration_creates_the_table_on_a_database_without_it():
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(
        engine, tables=[t for name, t in models.Base.metadata.tables.items() if name != "creative_takes"])
    path = Path(__file__).parents[1] / "alembic/versions/050_add_creative_takes.py"
    spec = importlib.util.spec_from_file_location("creative_takes_migration_fresh", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        inspector = inspect(connection)
        assert {c["name"] for c in inspector.get_columns("creative_takes")} == {
            "id", "restaurant_id", "surface", "period", "mode", "text", "evidence_hash", "llm_model",
            "prompt_version", "dropped_sentences", "created_at"}
        assert "ix_creative_takes_lookup" in {i["name"] for i in inspector.get_indexes("creative_takes")}
    engine.dispose()
