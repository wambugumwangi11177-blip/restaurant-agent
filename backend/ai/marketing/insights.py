"""
backend/ai/marketing/insights.py
─────────────────────────────────
GET /ai/marketing — a read-only, owner-facing view of the restaurant's growth
levers. Four parts:

  1. winback   — lapsed regulars (21+ days quiet), how many can legally be
                 reached, their combined past spend, and the exact message that
                 would be sent.
  2. audience  — how many customers a promo blast can reach right now (consent +
                 opt-out gated), plus the send-window and safety cap.
  3. history   — recent campaign/win-back/reminder sends, from the AgentMessage
                 log, so the owner can see what's already gone out.
  4. suggested_offers — the "offer engine": specific offers to run, each with a
                 plain-language WHY tied to the real numbers, a margin-safety
                 flag, and which send action the button should call.

Every figure traces to a deterministic module (winback = brain.get_winback_
candidates; puzzles = menu_engineer; spoilage = inventory_predictor). This file
invents no numbers, so the server-side grounding guarantee is untouched.
"""

from collections import defaultdict
from datetime import timedelta

from sqlalchemy.orm import Session

import models
from ai.analysis_clock import analysis_anchor

# Outbound message types that count as "a campaign" for the history view. The
# send choke point logs message_type as "<type>:<channel>" (e.g. promo:whatsapp)
# and sometimes raw (opt-out suppression), so we normalise on the part before ":".
CAMPAIGN_TYPES = {
    "promo": "Promo broadcasts",
    "campaign_winback": "Win-back campaigns",
    "no_show_winback": "No-show win-backs",
    "reservation_reminder": "Booking reminders",
}


def _base_type(message_type: str) -> str:
    return (message_type or "").split(":", 1)[0]


def get_marketing_insights(db: Session, restaurant_id: int) -> dict:
    """Read-only marketing intelligence for one restaurant."""
    from ai.whatsapp import brain

    now = analysis_anchor(db, restaurant_id)

    # ── 1. WIN-BACK ──────────────────────────────────────────────────────────
    candidates = brain.get_winback_candidates(db, restaurant_id)
    reachable = brain.winback_reachable(db, restaurant_id)
    past_spend_cents = sum(int(c.get("total_spend") or 0) for c in candidates)

    winback = {
        "lapse_days": brain.WINBACK_DAYS,
        "count": len(candidates),
        "reachable": reachable,
        "past_spend_cents": past_spend_cents,
        "candidates": [
            {
                "name": c.get("name") or "Valued customer",
                "days_away": c.get("days_away"),
                "total_spend_cents": int(c.get("total_spend") or 0),
                "order_count": c.get("order_count"),
                "fav_item": c.get("fav_item"),
                "message": c.get("message"),
            }
            for c in candidates[:10]
        ],
    }

    # ── 2. AUDIENCE / CONSENT ────────────────────────────────────────────────
    try:
        promo_reachable = brain.promo_audience_count(db, restaurant_id)
    except Exception:  # noqa: BLE001 — degrade, never crash the endpoint
        promo_reachable = 0

    consented_total = (
        db.query(models.CustomerConsent.customer_phone)
        .filter(models.CustomerConsent.restaurant_id == restaurant_id)
        .distinct()
        .count()
    )

    audience = {
        "promo_reachable": promo_reachable,
        "consented_customers": consented_total,
        "order_window_days": brain.PROMO_AUDIENCE_DAYS,
        "send_cap": brain.PROMO_MAX_RECIPIENTS,
    }

    # ── 3. CAMPAIGN HISTORY ──────────────────────────────────────────────────
    history = _campaign_history(db, restaurant_id, now)

    # ── 4. SUGGESTED OFFERS (the offer engine) ───────────────────────────────
    suggested_offers = _suggested_offers(db, restaurant_id, winback)

    return {
        "window_days": 30,
        "winback": winback,
        "audience": audience,
        "history": history,
        "suggested_offers": suggested_offers,
    }


def _campaign_history(db: Session, restaurant_id: int, now) -> list[dict]:
    """Last 90 days of outbound campaign activity, grouped by normalised type."""
    since = now - timedelta(days=90)
    rows = (
        db.query(models.AgentMessage)
        .filter(
            models.AgentMessage.restaurant_id == restaurant_id,
            models.AgentMessage.created_at >= since,
        )
        .all()
    )

    agg: dict[str, dict] = defaultdict(lambda: {"sent": 0, "other": 0, "last_sent": None})
    for m in rows:
        base = _base_type(m.message_type)
        if base not in CAMPAIGN_TYPES:
            continue
        bucket = agg[base]
        if m.status == "sent":
            bucket["sent"] += 1
        else:
            bucket["other"] += 1
        if m.created_at and (bucket["last_sent"] is None or m.created_at > bucket["last_sent"]):
            bucket["last_sent"] = m.created_at

    out = []
    for base, label in CAMPAIGN_TYPES.items():
        if base not in agg:
            continue
        b = agg[base]
        out.append({
            "type": base,
            "label": label,
            "sent": b["sent"],
            "not_delivered": b["other"],
            "last_sent": b["last_sent"].isoformat() if b["last_sent"] else None,
        })
    out.sort(key=lambda x: -(x["sent"] + x["not_delivered"]))
    return out


def _suggested_offers(db: Session, restaurant_id: int, winback: dict) -> list[dict]:
    """
    Deterministic offer engine. Each offer says WHAT to run, WHO it reaches, WHY
    it's worth it (in the owner's own numbers), whether the margin is safe, and
    which send action powers the button ("winback" → /ai/marketing/winback,
    "promo" → /ai/marketing/promo). Every source is wrapped so one failing module
    just drops its line instead of taking down the whole list.
    """
    offers: list[dict] = []

    # ── Offer 1: Win back lapsed regulars ────────────────────────────────────
    if winback["count"] > 0:
        n = winback["count"]
        reach = winback["reachable"]
        past = winback["past_spend_cents"]
        offers.append({
            "id": "winback",
            "type": "winback",
            "title": f"Win back {n} lapsed regular{'s' if n != 1 else ''}",
            "offer_text": "10% off your next visit",
            "audience_label": (
                f"{reach} reachable now"
                + (f" of {n} lapsed" if n != reach else "")
            ),
            "why": (
                f"{n} customer{'s' if n != 1 else ''} who used to order regularly "
                f"{'have' if n != 1 else 'has'} gone quiet for {winback['lapse_days']}+ days. "
                f"Their combined past spend is KES {past // 100:,}. A personal nudge naming "
                f"their favourite dish is the cheapest sale you can make — you already know they like you."
            ),
            "expected_impact_cents": None,
            "margin_safe": True,
            "margin_note": "A one-off 10% welcome-back discount still leaves a healthy margin on most dishes.",
            "source": "winback",
            "action": "winback",
            "reachable": reach,
        })

    # ── Offer 2: Promote a Puzzle (high margin, few order it) ─────────────────
    try:
        from ai.menu_engineer import get_menu_engineering
        menu = get_menu_engineering(db, restaurant_id)
        puzzles = [m for m in (menu.get("matrix") or []) if m.get("classification") == "Puzzle"]
        # Best puzzle = highest margin %, needs at least some sales history.
        puzzles.sort(key=lambda m: -(m.get("margin_pct") or 0))
        if puzzles:
            p = puzzles[0]
            offers.append({
                "id": f"promote_{p.get('id')}",
                "type": "promote",
                "title": f"Feature {p.get('name')} — high margin, few order it",
                "offer_text": f"Chef's pick this week: try our {p.get('name')}!",
                "audience_label": "Everyone who's opted in",
                "why": (
                    f"{p.get('name')} earns a healthy {p.get('margin_pct')}% margin but is under-ordered. "
                    f"Putting it in front of people — a WhatsApp shout-out, a bundle, or better menu placement — "
                    f"converts margin you already have. No discount needed, so every extra order is near-pure profit."
                ),
                "expected_impact_cents": None,
                "margin_safe": True,
                "margin_note": "This is a promotion, not a discount — margin is unchanged.",
                "source": "menu_puzzle",
                "action": "promo",
            })
    except Exception:  # noqa: BLE001
        pass

    # ── Offer 3: Move stock at spoilage risk before it's wasted ───────────────
    try:
        from ai.inventory_predictor import get_inventory_predictions
        inv = get_inventory_predictions(db, restaurant_id)
        at_risk = [
            p for p in (inv.get("predictions") or [])
            if (p.get("spoilage_risk") or 0) >= 70
        ]
        at_risk.sort(key=lambda p: -(p.get("spoilage_risk") or 0))
        if at_risk:
            item = at_risk[0]
            offers.append({
                "id": f"flash_{item.get('id') or item.get('name')}",
                "type": "flash",
                "title": f"Today-only special to move {item.get('name')}",
                "offer_text": f"Today only — special on dishes made with fresh {item.get('name')}!",
                "audience_label": "Everyone who's opted in",
                "why": (
                    f"You're holding {item.get('name')} at {item.get('spoilage_risk')}% spoilage risk. "
                    f"A quick same-day special turns stock you'd otherwise throw away into sales — "
                    f"you recover the cost instead of writing it off."
                ),
                "expected_impact_cents": None,
                "margin_safe": True,
                "margin_note": "Even a discounted sale beats spoilage — you recover cost that's otherwise lost.",
                "source": "inventory_spoilage",
                "action": "promo",
            })
    except Exception:  # noqa: BLE001
        pass

    return offers
