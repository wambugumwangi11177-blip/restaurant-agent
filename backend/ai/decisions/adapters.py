"""
backend/ai/decisions/adapters.py
───────────────────────────────────
Thin translators: each agent's existing output → a list of `Decision`s. These
NEVER recompute business logic — they read what the deterministic agents already
returned and reshape it into the shared `Decision` schema so it can be ranked.

Two honesty rules (directives/012):
  • Only pricing produces a real per-item monetary impact today
    (`monthly_impact_cents`), so only pricing decisions carry
    `impact_cents_month`. Operational recommendations (reorder, staffing,
    supplier, menu, marketing) are left `impact_cents_month=None` — "not
    quantified" — rather than inventing a number. They still rank on confidence,
    risk and effort.
  • Confidence is derived from signals the agent already emitted
    (recommendation_strength, priority), never guessed.

Every adapter is defensive: a single failing/renamed upstream function degrades
to "no decisions from that source", never a 500 for the whole endpoint.
"""

from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from .model import Decision

logger = logging.getLogger("ai.decisions")


# Priority string (used across supply/labor/inventory/menu recs) → confidence.
_PRIORITY_CONFIDENCE = {
    "CRITICAL": 90, "HIGH": 80, "MEDIUM": 65, "LOW": 50, "INFO": 40,
}
# Placeholder "recommendations" that are really empty-state notices, not actions.
_NON_ACTION_PRIORITIES = {"INFO"}


def _priority(rec: dict) -> str:
    return str(rec.get("priority", "MEDIUM")).upper()


# ─────────────────────────────────────────────────────────────────────────────
# PRICING — the one source with a real per-item monetary impact
# ─────────────────────────────────────────────────────────────────────────────

# Doing the change is one click (approve endpoint exists) → difficulty 1.
# Risk reflects the downside of the price move itself.
_PRICING_RISK = {"REPRICE": 2, "SURGE": 3, "STIMULATE": 3}


def from_pricing(db: Session, restaurant_id: int) -> list[Decision]:
    from ai.pricing.recommendations import get_pricing_intelligence

    data = get_pricing_intelligence(db, restaurant_id)
    out: list[Decision] = []
    for rec in data.get("recommendations", []):
        rtype = rec.get("type")
        if not rtype:
            continue
        suggested = rec.get("suggested_price", 0)
        out.append(Decision(
            agent="pricing_intelligence",
            category="pricing",
            action=f"{rtype.title()}: set {rec.get('item_name', 'item')} to "
                   f"KES {suggested // 100:,} (from KES {rec.get('current_price', 0) // 100:,})",
            rationale=rec.get("reason", ""),
            confidence_pct=int(rec.get("recommendation_strength", 0)),
            risk=_PRICING_RISK.get(rtype, 3),
            difficulty=1,
            impact_cents_month=rec.get("monthly_impact_cents"),
            data_sources=["orders (30-day velocity)", "menu_items.cost_price"],
            alternatives=["Keep current price", "Reject recommendation"],
            entity_type="menu_item",
            entity_id=rec.get("item_id"),
            meta={
                "type": rtype,
                "price_change_pct": rec.get("price_change_pct"),
                "when_to_apply": rec.get("when"),
            },
        ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Generic operational recommendations (supply-chain / labor / menu)
# ─────────────────────────────────────────────────────────────────────────────

def _from_generic_recs(
    recs: list[dict], agent: str, category: str,
    default_risk: int, default_difficulty: int,
    data_sources: list[str],
) -> list[Decision]:
    """Reshape a list of {priority, message, action} recs into Decisions."""
    out: list[Decision] = []
    for rec in recs or []:
        priority = _priority(rec)
        if priority in _NON_ACTION_PRIORITIES:
            continue
        action = rec.get("action") or rec.get("message") or ""
        rationale = rec.get("message") or rec.get("reason") or rec.get("action") or ""
        if not action:
            continue
        out.append(Decision(
            agent=agent,
            category=category,
            action=str(action),
            rationale=str(rationale),
            confidence_pct=_PRIORITY_CONFIDENCE.get(priority, 60),
            risk=default_risk,
            difficulty=default_difficulty,
            impact_cents_month=None,   # not quantified by these agents
            data_sources=data_sources,
            meta={"priority": priority},
        ))
    return out


def from_supply_chain(db: Session, restaurant_id: int) -> list[Decision]:
    from ai.supply_chain.intelligence import get_supply_chain_intelligence
    data = get_supply_chain_intelligence(db, restaurant_id)
    return _from_generic_recs(
        data.get("recommendations", []), "supply_chain", "supply_chain",
        default_risk=2, default_difficulty=3,
        data_sources=["purchase_orders", "suppliers.reliability_score"],
    )


def from_labor(db: Session, restaurant_id: int) -> list[Decision]:
    from ai.labor.intelligence import get_labor_intelligence
    data = get_labor_intelligence(db, restaurant_id)
    return _from_generic_recs(
        data.get("recommendations", []), "labor_intelligence", "labor",
        default_risk=3, default_difficulty=3,
        data_sources=["labor_shifts", "orders (revenue)"],
    )


def from_menu(db: Session, restaurant_id: int) -> list[Decision]:
    from ai.menu_engineer import get_menu_engineering
    data = get_menu_engineering(db, restaurant_id)
    return _from_generic_recs(
        data.get("recommendations", []), "menu_engineer", "menu",
        default_risk=2, default_difficulty=2,
        data_sources=["order_items", "menu_items"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Inventory — reorder / critical stock items become decisions
# ─────────────────────────────────────────────────────────────────────────────

def from_inventory(db: Session, restaurant_id: int) -> list[Decision]:
    from ai.inventory_predictor import get_inventory_predictions
    data = get_inventory_predictions(db, restaurant_id)

    out: list[Decision] = []
    for p in data.get("predictions", []):
        status = p.get("status")
        if status not in ("critical", "low", "reorder"):
            continue
        name = p.get("name") or p.get("item_name") or "item"
        # Acting (placing a reorder) is low risk; NOT acting is the risk. The
        # decision's own risk is the downside of doing it → low. Criticality
        # raises confidence and urgency, not the risk of reordering.
        confidence = {"critical": 90, "low": 75, "reorder": 70}.get(status, 70)
        out.append(Decision(
            agent="inventory_predictor",
            category="inventory",
            action=f"Reorder {name}"
                   + (" now — critical" if status == "critical" else " soon"),
            rationale=p.get("recommendation") or p.get("reason")
                      or f"Stock status: {status}",
            confidence_pct=confidence,
            risk=2,
            difficulty=3,
            impact_cents_month=None,
            data_sources=["inventory_items", "stock_movements"],
            entity_type="inventory_item",
            entity_id=p.get("item_id") or p.get("id"),
            meta={"status": status},
        ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Marketing — a win-back opportunity when lapsed regulars are reachable
# ─────────────────────────────────────────────────────────────────────────────

def from_marketing(db: Session, restaurant_id: int) -> list[Decision]:
    from ai.marketing import get_marketing_insights
    data = get_marketing_insights(db, restaurant_id)

    winback = data.get("winback", {})
    reachable = int(winback.get("reachable") or 0)
    if reachable <= 0:
        return []

    # past_spend_cents is lifetime spend of lapsed regulars — an at-risk figure,
    # NOT a monthly impact. Kept in meta, deliberately not set as
    # impact_cents_month, so ranking never treats it as recurring monthly profit.
    return [Decision(
        agent="marketing",
        category="marketing",
        action=f"Send win-back offer to {reachable} lapsed regular(s)",
        rationale=f"{winback.get('count', reachable)} regulars haven't returned in "
                  f"{winback.get('lapse_days', 30)}+ days; {reachable} are reachable "
                  f"(consented, not opted out).",
        confidence_pct=65,
        risk=2,
        difficulty=1,   # one owner-triggered action (POST /ai/marketing/winback)
        impact_cents_month=None,
        data_sources=["orders (recency)", "customer_consents"],
        alternatives=["Send a broad promo instead", "Do nothing"],
        meta={
            "reachable": reachable,
            "at_risk_spend_cents": int(winback.get("past_spend_cents") or 0),
        },
    )]


# ─────────────────────────────────────────────────────────────────────────────
# Aggregator
# ─────────────────────────────────────────────────────────────────────────────

_ADAPTERS = {
    "pricing": from_pricing,
    "inventory": from_inventory,
    "supply_chain": from_supply_chain,
    "menu": from_menu,
    "labor": from_labor,
    "marketing": from_marketing,
}


def collect_decisions(
    db: Session, restaurant_id: int, sources: list[str] | None = None
) -> list[Decision]:
    """
    Gather Decisions from every (or a subset of) agent. Each source runs in
    isolation: one failing adapter never sinks the rest.
    """
    chosen = sources or list(_ADAPTERS.keys())
    decisions: list[Decision] = []
    for name in chosen:
        adapter = _ADAPTERS.get(name)
        if adapter is None:
            continue
        try:
            decisions.extend(adapter(db, restaurant_id))
        except Exception as exc:  # noqa: BLE001 — degrade per-source, never 500
            logger.warning("decision adapter '%s' failed: %s", name, exc)
    return decisions
