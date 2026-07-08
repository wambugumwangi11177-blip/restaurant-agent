"""
Tests for the number-faithfulness guard (ai/reasoning/grounding.py).

Pure functions, no LLM/network — these lock in the exact behaviour that makes an
LLM narrative safe to show: correct figures survive, invented ones get redacted.
"""
from ai.reasoning import grounding


PAYLOAD = {
    "summary": {"avg_margin_pct": 58.3, "profit_cents": 1470000},
    "channels": [
        {"channel": "uber_eats", "commission_pct": 25, "revenue_cents": 900000},
        {"channel": "walk_in", "net_margin_pct": 61.0},
    ],
    "items": [{"name": "Beef Burger", "sold": 812, "margin_pct": 22.0}],
}


def _verify(headline="", priorities=None, actions=None):
    return grounding.verify(
        {"headline": headline, "priorities": priorities or [], "actions": actions or []},
        PAYLOAD,
    )


def test_grounded_percentage_survives():
    # 25% is literally in the payload (commission_pct: 25)
    out = _verify(headline="Commission runs at 25% on delivery.")
    assert out["verified"] is True
    assert "25%" in out["headline"]
    assert out["ungrounded_numbers"] == []


def test_invented_percentage_is_redacted_and_reported():
    # 23% appears nowhere; the real figure is 25%
    out = _verify(headline="Commission runs at 23% on delivery.")
    assert out["verified"] is False
    assert "23%" in out["ungrounded_numbers"]
    assert "23%" not in out["headline"]
    assert grounding._REDACTION in out["headline"]


def test_rounded_figure_grounds_against_source():
    # model rounds 58.3 -> 58%; should be accepted, not flagged
    out = _verify(headline="Margins sit around 58%.")
    assert out["verified"] is True
    assert "58%" in out["headline"]


def test_cents_rendered_as_currency_grounds():
    # 900000 cents shown as KES 9,000 — a legitimate derivation
    out = _verify(priorities=["Delivery brings in KES 9,000."])
    assert out["verified"] is True
    assert out["ungrounded_numbers"] == []


def test_volume_number_grounds():
    out = _verify(actions=[{"action": "Reprice", "why": "Beef Burger sold 812", "impact": "x"}])
    assert out["verified"] is True


def test_small_bare_integers_are_not_policed():
    # "3 channels" is a count, not in the value set, but must not be flagged
    out = _verify(headline="You have 3 delivery channels to watch.")
    assert out["verified"] is True
    assert "3" in out["headline"]


def test_invented_number_inside_action_is_redacted():
    out = _verify(actions=[{"action": "Cut waste", "why": "food cost hit 47%", "impact": "save more"}])
    assert out["verified"] is False
    assert "47%" in out["ungrounded_numbers"]
    assert "47%" not in out["actions"][0]["why"]


def test_qualitative_narrative_is_always_verified():
    out = _verify(
        headline="Delivery is your least profitable channel.",
        priorities=["Your bestseller carries a thin margin."],
    )
    assert out["verified"] is True
    assert out["ungrounded_numbers"] == []
