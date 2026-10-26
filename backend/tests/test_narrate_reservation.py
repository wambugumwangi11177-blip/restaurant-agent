"""narrate() reserves its estimated cost, releases the tenant lock, then calls the provider.

A slow model must not hold a database lock, while two simultaneous calls still cannot spend the same
remaining budget. The reservation is a usage row that is rewritten with the real numbers (or removed).
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import models
from ai import llm_client, spend_cap
from ai.cost_model import cost_usd
from ai.owner_narrative import narrate
from tests.test_overview_scope import scoped_owner  # noqa: F401

RID = 202
SYSTEM = "Be brief."
MESSAGES = [{"role": "user", "content": "How are sales?"}]
MAX_TOKENS = 200


def _reply(text="Revenue is KSh 500.", tokens=(120, 30)):
    return SimpleNamespace(text=text, model="test-model",
                           usage=SimpleNamespace(input_tokens=tokens[0], output_tokens=tokens[1]))


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(llm_client, "model_for_tier", lambda _tier: "test-model")


def _call(db, user):
    return narrate(db, user, RID, MESSAGES, SYSTEM, MAX_TOKENS, "test-v1")


def test_the_transaction_is_committed_before_the_provider_is_called(db_session, scoped_owner, provider, monkeypatch):
    user, _ = scoped_owner
    events = []
    real_commit = db_session.commit

    def commit():
        events.append("commit")
        real_commit()

    def reply(messages, **kwargs):
        events.append("provider")
        return _reply()

    monkeypatch.setattr(db_session, "commit", commit)
    monkeypatch.setattr(llm_client, "chat_with_usage", reply)
    assert _call(db_session, user) == "Revenue is KSh 500."
    # reserve and release the lock, then the slow call, then record what was really used
    assert events == ["commit", "provider", "commit"]


def test_the_reservation_counts_against_the_budget_while_the_call_is_in_flight(db_session, scoped_owner, provider, monkeypatch):
    user, _ = scoped_owner
    seen = {}

    def reply(messages, **kwargs):
        seen["rows"] = db_session.query(models.TokenUsage).count()
        seen["spent"] = spend_cap.today_spend_usd(db_session, RID)
        return _reply()

    monkeypatch.setattr(llm_client, "chat_with_usage", reply)
    _call(db_session, user)
    assert seen["rows"] == 1 and seen["spent"] > 0                     # reserved before the provider answered
    usage = db_session.query(models.TokenUsage).one()                  # and rewritten, not duplicated, afterwards
    assert (usage.restaurant_id, usage.llm_model, usage.input_tokens, usage.output_tokens, usage.prompt_version) == (
        RID, "test-model", 120, 30, "test-v1")
    assert spend_cap.today_spend_usd(db_session, RID) == pytest.approx(cost_usd("test-model", 120, 30))


def test_a_second_call_cannot_spend_the_budget_the_first_has_reserved(db_session, scoped_owner, provider, monkeypatch):
    user, _ = scoped_owner
    input_bound = len(SYSTEM.encode()) + len(MESSAGES[0]["content"].encode()) + 1024
    one_call = cost_usd("test-model", input_bound, MAX_TOKENS)
    monkeypatch.setattr(spend_cap, "DAILY_LLM_SPEND_CAP_USD", one_call * 1.5)    # room for one call, not two
    outcome = {}

    def reply(messages, **kwargs):
        try:
            _call(db_session, user)                                    # a simultaneous request, while the first is in flight
            outcome["second"] = "allowed"
        except HTTPException as exc:
            outcome["second"] = exc.status_code
        return _reply()

    monkeypatch.setattr(llm_client, "chat_with_usage", reply)
    _call(db_session, user)
    assert outcome["second"] == 429
    assert db_session.query(models.TokenUsage).count() == 1


def test_a_failed_provider_call_gives_the_reservation_back(db_session, scoped_owner, provider, monkeypatch):
    user, _ = scoped_owner

    def broken(messages, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(llm_client, "chat_with_usage", broken)
    with pytest.raises(RuntimeError):
        _call(db_session, user)
    assert db_session.query(models.TokenUsage).count() == 0
    assert spend_cap.today_spend_usd(db_session, RID) == 0


def test_a_spent_budget_stops_the_call_before_anything_is_reserved(db_session, scoped_owner, provider, monkeypatch):
    user, _ = scoped_owner
    calls = []
    monkeypatch.setattr(llm_client, "chat_with_usage", lambda *a, **k: calls.append(1) or _reply())
    monkeypatch.setattr(spend_cap, "DAILY_LLM_SPEND_CAP_USD", 0)
    with pytest.raises(HTTPException) as caught:
        _call(db_session, user)
    assert caught.value.status_code == 429
    assert not calls
    assert db_session.query(models.TokenUsage).count() == 0


def test_a_failure_while_recording_usage_keeps_the_estimate_and_still_returns_the_text(db_session, scoped_owner, provider, monkeypatch):
    user, _ = scoped_owner
    monkeypatch.setattr(llm_client, "chat_with_usage", lambda *a, **k: _reply())
    real_commit = db_session.commit
    commits = []

    def commit():
        commits.append(1)
        if len(commits) == 2:                    # the first commit reserves; the second records the real usage
            raise RuntimeError("database blip")
        real_commit()

    monkeypatch.setattr(db_session, "commit", commit)
    assert _call(db_session, user) == "Revenue is KSh 500."
    usage = db_session.query(models.TokenUsage).one()
    assert usage.input_tokens > 120 and usage.output_tokens == MAX_TOKENS      # the estimate stayed: over-counted, not lost
