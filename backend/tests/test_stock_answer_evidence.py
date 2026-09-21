"""Threshold alerts must not masquerade as measured stockout forecasts."""
from routers.ai_ask import _answer_stock
from ai import inventory_predictor


def test_threshold_alert_without_usage_does_not_claim_forecast(monkeypatch):
    monkeypatch.setattr(inventory_predictor, "get_inventory_predictions", lambda *args: {
        "predictions": [{"item_name": "Tomatoes", "status": "low"}]})
    card = _answer_stock(None, 1, "What stock is low?")
    assert "below reorder point" in card["finding"]
    assert "threshold" in card["why"]
    assert "timing is unavailable" in card["steps"][0]["why"]
    assert "14 days" not in str(card)
    assert card["data"]["stockout_timing_available"] is False
    assert card["data"]["narrative_allowed"] is False


def test_empty_predictions_do_not_assert_stock_is_safe(monkeypatch):
    monkeypatch.setattr(inventory_predictor, "get_inventory_predictions", lambda *args: {})
    card = _answer_stock(None, 1, "What stock is low?")
    assert "Missing usage history" in card["why"]
    assert "No reorder needed" not in card["recommendation"]


def test_measured_stockout_prediction_can_be_narrated(monkeypatch):
    monkeypatch.setattr(inventory_predictor, "get_inventory_predictions", lambda *args: {
        "predictions": [{"item_name": "Tomatoes", "status": "low", "days_until_stockout": 2}]})
    card = _answer_stock(None, 1, "What will run out soon?")
    assert "projected" in card["finding"]
    assert card["data"]["stockout_timing_available"] is True
    assert card["data"]["narrative_allowed"] is True


def test_threshold_chat_skips_unverifiable_narrative(monkeypatch, db_session):
    import models
    from routers import ai_ask
    from ai import llm_client
    from rate_limit import limiter

    restaurant = models.Restaurant(name="Threshold only")
    db_session.add(restaurant)
    db_session.commit()

    # chat_llm is rate-limited, so slowapi rejects a direct call that carries no
    # ASGI Request. The limit is not what this test is about; turn it off and
    # pass request=None. _with_provenance does need a real session (it reads the
    # restaurant's data freshness and analysis anchor), hence db_session.
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(ai_ask, "_restaurant_id", lambda *args: restaurant.id)
    monkeypatch.setattr(inventory_predictor, "get_inventory_predictions", lambda *args: {
        "predictions": [{"item_name": "Tomatoes", "status": "low"}]})
    monkeypatch.setattr(llm_client, "is_available", lambda: True)

    calls = []

    def forbidden_chat(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Threshold-only evidence must not reach free-form narration")

    monkeypatch.setattr(llm_client, "chat", forbidden_chat)
    monkeypatch.setattr(llm_client, "chat_with_usage", forbidden_chat)
    result = ai_ask.chat_llm(None, ai_ask.ChatBody(question="What will run out soon?"),
                             db_session, None)
    assert result["llm_used"] is False
    assert result["llm_reply"] is None
    assert calls == []
    assert "Stockout timing is not established" in result["grounded"]["why"]
