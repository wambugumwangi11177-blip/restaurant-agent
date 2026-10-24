"""A mocked model that invents figures is retried once, then only the bad sentences go.

Also locks the cases the click-through hit: a decimal must stay "3.8", a list
number and a small count are words, dollars never enter the ROI speech, and the
allowed-figures list is already written in KES.
"""
import json
from types import SimpleNamespace

from ai import llm_client
from ai.reasoning import grounding, narrator


def _reply(text: str):
    return SimpleNamespace(text=text, model="stub-retry", usage=SimpleNamespace(input_tokens=3, output_tokens=3))


def test_a_decimal_stays_one_number():
    out = grounding.verify({"headline": "The kitchen counted 3.8 kg of beef."}, {"counted_kg": 3.8})
    assert out["verified"] is True
    assert out["headline"] == "The kitchen counted 3.8 kg of beef."
    assert "3. 8" not in out["headline"]


def test_list_numbering_and_small_counts_are_not_figures():
    out = grounding.verify(
        {"headline": "1. Two ideas for the weekend.\n2. Keep the grill warm. There are 2 ideas."},
        {},
    )
    assert out["verified"] is True
    assert out["ungrounded_numbers"] == []
    invented = grounding.verify({"headline": "There are 12 ideas."}, {})
    assert invented["verified"] is False


def test_allowed_figures_are_kes_and_name_the_dish():
    block = grounding.allowed_figures_block({
        "revenue_cents": 1_634_000,
        "food_cost_pct": 29.4,
        "orders": 17,
        "token_usd": 0.04,
        "aside": "worth $50",
        "dish": "Nyama choma",
    })
    assert "KES 16,340" in block
    assert "29.4%" in block
    assert "orders: 17" in block
    assert "Nyama choma" in block
    assert "$50" not in block and "0.04" not in block


def test_narrator_retries_once_naming_the_offending_numbers_then_keeps_the_rewrite(monkeypatch):
    narrator._cache.clear()
    prompts = []

    def chat(**kwargs):
        prompts.append(kwargs["messages"][0]["content"])
        if len(prompts) == 1:
            return _reply('{"headline": "Margin will hit $5,000 and 64%.", "priorities": [], "actions": []}')
        return _reply('{"headline": "The grill is the dish to watch.", "priorities": [], "actions": []}')

    monkeypatch.setattr(llm_client, "is_available", lambda: True)
    monkeypatch.setattr(llm_client, "chat_with_usage", chat)
    result = narrator.narrate(
        {"summary": {"gross_margin_pct": 29.4}, "recommendations": [{"dish": "Nyama choma", "action": "promote"}]},
        "profit",
    )
    assert len(prompts) == 2
    assert "$5,000" in prompts[1] or "$" in prompts[1]
    assert "64%" in prompts[1]
    assert "Allowed figures" in prompts[0]
    assert "Nyama choma" in prompts[0]
    assert result["headline"] == "The grill is the dish to watch."
    assert result["verified"] is True
    data = prompts[0].split("<data>\n", 1)[1].split("\n</data>", 1)[0]
    assert "$" not in data


def test_roi_speech_carries_kes_and_no_dollar_or_raw_multiple():
    speech = narrator._roi_for_speech({
        "window_days": 30,
        "time_saved": {"hours_saved_30d": 12, "money_saved_cents": 500_000},
        "money_captured": {"monthly_impact_cents": 120_000, "recommendations_approved": 2},
        "economics": {"ai_cost_cents": 80, "value_delivered_cents": 620_000, "roi_multiple": 2334.8},
    })
    blob = json.dumps(speech)
    assert "$" not in speech["staff_time_worth"] and "$" not in speech["model_spend"]
    assert "2334" not in blob and "roi_multiple" not in speech
    assert speech["staff_time_worth"] == "KES 5,000"
    assert "multiple" in speech["say"] and "$" in speech["say"]
