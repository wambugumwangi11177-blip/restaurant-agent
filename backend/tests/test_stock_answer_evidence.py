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


def test_empty_predictions_do_not_assert_stock_is_safe(monkeypatch):
    monkeypatch.setattr(inventory_predictor, "get_inventory_predictions", lambda *args: {})
    card = _answer_stock(None, 1, "What stock is low?")
    assert "Missing usage history" in card["why"]
    assert "No reorder needed" not in card["recommendation"]
