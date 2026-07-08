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


# ── Negative figures ──────────────────────────────────────────────────────────
#
# The profit payload routinely carries a negative `revenue_mom_pct`, and the
# most important sentence an owner reads is "Revenue down 15%". Before the
# 2026-07-08 fix the regex matched no minus sign and the grounded set held only
# signed values, so every negative was unmatchable — the guard redacted the
# correct figure and flipped verified=False.

NEG_PAYLOAD = {"summary": {"revenue_mom_pct": -15.0, "profit_cents": -250000}}


def _verify_neg(headline):
    return grounding.verify({"headline": headline, "priorities": [], "actions": []}, NEG_PAYLOAD)


def test_negative_payload_grounds_sign_carried_by_prose():
    # "down 15%" — the sign lives in the word, not the digits
    out = _verify_neg("Revenue down 15% this month.")
    assert out["verified"] is True, out["ungrounded_numbers"]
    assert "15%" in out["headline"]


def test_negative_payload_grounds_explicit_minus():
    out = _verify_neg("Revenue is -15% MoM.")
    assert out["verified"] is True, out["ungrounded_numbers"]
    assert "-15%" in out["headline"]


def test_negative_payload_grounds_bare_magnitude():
    out = _verify_neg("Revenue fell 15%.")
    assert out["verified"] is True, out["ungrounded_numbers"]


def test_negative_cents_render_as_currency():
    # -250000 cents -> "KES 2,500" of lost profit
    out = _verify_neg("You lost KES 2,500 in profit.")
    assert out["verified"] is True, out["ungrounded_numbers"]


def test_wrong_negative_is_still_redacted():
    # -23% is NOT -15%; the guard must not go blind to sign just to allow it
    out = _verify_neg("Revenue down 23% this month.")
    assert out["verified"] is False
    assert "23%" in out["ungrounded_numbers"]
    assert grounding._REDACTION in out["headline"]


def test_wrong_explicit_negative_is_still_redacted():
    out = _verify_neg("Revenue is -23% MoM.")
    assert out["verified"] is False
    assert "-23%" in out["ungrounded_numbers"]


def test_large_bare_negative_is_policed():
    # abs() magnitude test: "-500" is a big figure, not a small bare integer
    out = _verify_neg("Profit moved -500 on the week.")
    assert out["verified"] is False
    assert "-500" in out["ungrounded_numbers"]


# ── Hyphens that are not minus signs ──────────────────────────────────────────

def test_iso_date_is_not_read_as_negative_numbers():
    # "2026" is ungrounded and gets redacted, but -07 / -08 must not be invented
    out = _verify_neg("Compared with 2026-07-08 figures.")
    assert "-7" not in out["ungrounded_numbers"]
    assert "-8" not in out["ungrounded_numbers"]


def test_range_hyphen_is_not_read_as_negative():
    out = _verify_neg("Margins ran 15-20% last week.")
    # the second figure is read as 20, not -20
    assert "-20%" not in out["ungrounded_numbers"]


# ── Derivation-set tightening ─────────────────────────────────────────────────

def test_rounded_cent_derivation_does_not_ground_unrelated_percent():
    """
    round(2547 / 100) == 25 used to be in the grounded set, so an invented "25%"
    could ground itself against an unrelated order count of 2547. Tolerance
    alone (|25 - 25.47| > 1% of 25.47) correctly rejects it.
    """
    out = grounding.verify(
        {"headline": "Commission runs at 25%.", "priorities": [], "actions": []},
        {"total_orders_30d": 2547},
    )
    assert out["verified"] is False
    assert "25%" in out["ungrounded_numbers"]


def test_model_rounding_of_a_derived_figure_still_grounds():
    # 900000 cents -> 9000.00; "KES 9,000" must still pass via ÷100 + tolerance
    out = grounding.verify(
        {"headline": "Delivery brought KES 9,000.", "priorities": [], "actions": []},
        {"revenue_cents": 900000},
    )
    assert out["verified"] is True, out["ungrounded_numbers"]
