"""The creative insight beside a deterministic answer.

The model is stubbed. One test walks a real tool call (sales) and checks the
note can cite only what that tool returned. A failure leaves the computed
answer in place and is logged.
"""
import logging
from types import SimpleNamespace

import pytest

import auth
import models
from ai import insight, llm_client
from ai import spend_cap
from owner.ask import ask
from owner.home import compose_home, compose_home_notes
from owner.reports import compose_report, compose_report_notes
from owner.states import OwnerContext
from time_utils import utcnow


@pytest.fixture(autouse=True)
def _quiet_insight_state():
    insight.reset_runtime_state()
    yield
    insight.reset_runtime_state()


def _fresh(db, suffix):
    tenant = models.Tenant(name=f"Insight {suffix}")
    db.add(tenant)
    db.flush()
    restaurant = models.Restaurant(tenant_id=tenant.id, name=f"Insight {suffix}", address="Nairobi")
    user = models.User(
        tenant_id=tenant.id, email=f"{suffix}@insight.test", hashed_password=auth.get_password_hash("x"),
        role=models.Role.STAFF, staff_role=models.StaffRole.OWNER, token_version=0,
    )
    db.add_all([restaurant, user])
    db.commit()
    return restaurant, user


def _order(db, restaurant_id, total_cents):
    db.add(models.Order(
        restaurant_id=restaurant_id, is_paid=True, total=total_cents,
        status=models.OrderStatus.SERVED, created_at=utcnow(),
    ))
    db.commit()


def _tool_turn(name, arguments):
    return SimpleNamespace(
        stop_reason="tool_use",
        content=[SimpleNamespace(type="tool_use", id="t1", name=name, input=arguments)],
        model="stub-model",
        usage=SimpleNamespace(input_tokens=20, output_tokens=10),
    )


def _prose(text):
    return SimpleNamespace(
        stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text=text)],
        model="stub-model",
        usage=SimpleNamespace(input_tokens=30, output_tokens=15),
    )


def _enable(monkeypatch, chat):
    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(llm_client, "model_for_tier", lambda tier: "stub-model")
    monkeypatch.setattr(llm_client, "chat_with_tools", chat)

    def usage(messages, system="", max_tokens=1024, tier=None, temperature=0, extra_body=None):
        return SimpleNamespace(text="Revenue is KSh 500.", model="stub-model",
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    monkeypatch.setattr(llm_client, "chat_with_usage", usage)
    monkeypatch.setenv("FEATURE_CREATIVE_LAYER", "true")
    monkeypatch.setenv("FEATURE_AI_NARRATION", "true")


def _tool_results(messages):
    found = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                found.append(block["content"])
    return found


def test_ask_insight_calls_sales_and_drops_an_unbacked_figure(db_session, monkeypatch):
    restaurant, user = _fresh(db_session, "round")
    other, _owner = _fresh(db_session, "other")
    _order(db_session, restaurant.id, 50000)
    _order(db_session, other.id, 99900)
    calls = []

    def chat(messages, tools, system="", max_tokens=1024, model=None, tier=None, temperature=None):
        calls.append(messages)
        if len(calls) % 2 == 1:
            assert "sales" in {tool["name"] for tool in tools}
            assert temperature == insight.creative.TEMPERATURE
            return _tool_turn("sales", {"window": "today", "restaurant_id": other.id})
        return _prose("Paid sales are KSh 500. A mystery total of KSh 999,999 is not in the records.")

    _enable(monkeypatch, chat)
    ctx = OwnerContext(db_session, user, restaurant)
    before = db_session.query(models.Order).filter_by(restaurant_id=restaurant.id).count()
    answer = ask(ctx, "How were sales today?")
    assert answer["headline"].startswith("Revenue today is")
    assert answer["insight"]["label"] == insight.LABEL
    assert answer["insight"]["state"] == "live"
    assert "KES 500" in answer["insight"]["text"]
    assert "999,999" not in answer["insight"]["text"]
    assert answer["insight"]["text"] != answer["headline"]
    results = _tool_results(calls[1])
    assert any('"revenue_kes": 500' in result for result in results)
    assert all('"revenue_kes": 999' not in result for result in results)
    assert db_session.query(models.Order).filter_by(restaurant_id=restaurant.id).count() == before
    assert db_session.query(models.TokenUsage).filter_by(restaurant_id=restaurant.id, prompt_version="insight-v1").count() == 2

    again = ask(ctx, "How were sales today?")
    assert again["headline"] == answer["headline"]
    assert again["insight"]["text"] == answer["insight"]["text"]
    assert len(calls) == 2


def test_insight_failure_keeps_the_deterministic_answer_and_is_logged(db_session, monkeypatch, caplog):
    restaurant, user = _fresh(db_session, "down")
    _order(db_session, restaurant.id, 20000)

    def chat(messages, tools, system="", max_tokens=1024, model=None, tier=None, temperature=None):
        raise RuntimeError("provider down")

    _enable(monkeypatch, chat)
    with caplog.at_level(logging.WARNING, logger="ai.insight"):
        answer = ask(OwnerContext(db_session, user, restaurant), "How were sales today?")
    assert answer["headline"].startswith("Revenue today is")
    assert answer["insight"]["state"] == "unavailable"
    assert answer["insight"]["note"] == "insight unavailable"
    assert answer["insight"]["text"] is None
    assert any("insight failed" in record.message and "provider down" in record.message for record in caplog.records)


def test_insight_stops_at_the_spend_cap(db_session, monkeypatch, caplog):
    restaurant, user = _fresh(db_session, "cap")
    calls = []

    def chat(messages, tools, system="", max_tokens=1024, model=None, tier=None, temperature=None):
        calls.append(1)
        return _prose("Paid sales are KSh 0.")

    _enable(monkeypatch, chat)
    monkeypatch.setattr(spend_cap, "DAILY_LLM_SPEND_CAP_USD", 0.0)
    with caplog.at_level(logging.WARNING, logger="ai.insight"):
        got = insight.attach(
            db_session, user, restaurant.id, surface="ask", question="How were sales today?",
            data={"headline": "Revenue today is KSh 0 across 0 paid orders."},
        )
    assert calls == []
    assert got["note"] == "insight unavailable"
    assert any("insight failed" in record.message for record in caplog.records)


def test_home_and_report_keep_their_figures(db_session, monkeypatch):
    restaurant, user = _fresh(db_session, "pages")
    _order(db_session, restaurant.id, 50000)
    calls = []

    def chat(messages, tools, system="", max_tokens=1024, model=None, tier=None, temperature=None):
        calls.append(1)
        if len(calls) % 2 == 1:
            return _tool_turn("sales", {"window": "today"})
        return _prose("Paid sales are KSh 500.")

    _enable(monkeypatch, chat)
    ctx = OwnerContext(db_session, user, restaurant)
    home = compose_home(ctx, "today")
    assert home["pulse"]["sales_today"] == 500.0
    assert home["pulse"]["orders_today"] == 1
    assert "insight" not in home
    assert calls == []

    notes = compose_home_notes(ctx, "today")
    assert notes["insight"]["text"] == "Paid sales are KES 500."
    assert "Paid sales are KES 500." not in str(home["pulse"])

    report = compose_report(ctx, "daily")
    sales = next(section for section in report["sections"] if section["key"] == "sales")
    assert "insight" not in report
    report_notes = compose_report_notes(ctx, "daily")
    assert report_notes["insight"]["label"] == insight.LABEL
    assert report_notes["insight"]["text"] not in (sales.get("headline") or "")
    assert sales["state"] in ("live", "no_data", "stale", "learning")


def test_insight_is_left_out_when_the_creative_layer_is_off(db_session, monkeypatch):
    restaurant, user = _fresh(db_session, "off")
    _order(db_session, restaurant.id, 50000)
    monkeypatch.setattr(llm_client, "is_available", lambda: False)
    monkeypatch.setenv("FEATURE_CREATIVE_LAYER", "false")
    answer = ask(OwnerContext(db_session, user, restaurant), "How were sales today?")
    assert "insight" not in answer
    assert answer["headline"].startswith("Revenue today is")
