"""
backend/ai/decisions/adapters.py
───────────────────────────────────
Thin translators: each agent's existing output → a list of `Decision`s. These
NEVER recompute business logic — they read what the deterministic agents already
returned and reshape it into the shared `Decision` schema so it can be ranked.

Two honesty rules (directives/012):
  • `impact_cents_month` is set only where an engine measured money: pricing
    (`monthly_impact_cents`), and — S4.2 — the four signals the owner's own
    screens already show in KES: missing stock (the gap × the item's cost), a
    drawer that is short again and again, a dish charged below its menu price,
    and a delivery platform whose commission pushes a dish under the floor.
    Each is the engine's figure said as a month, nothing more. Operational
    recommendations (reorder, staffing, supplier, menu, marketing) are left
    `impact_cents_month=None` — "not quantified" — rather than inventing a
    number. They still rank on confidence, risk and effort.
  • A decision that rests on one of the owner's settings says which, in
    `meta["assumption"]`, so the card can show "Based on: your floor 40%".
  • `meta["kind"]` says whether the figure is money already going out ("loss": a stock gap, a short drawer, a dish charged
    or priced below the floor, a platform's commission) or money you could make ("idea": a price rise on what sells hot, a
    discount on what sells slowly). Home ranks losses before ideas of the same worth: "costing you money" is about the first.
  • Confidence is derived from signals the agent already emitted
    (recommendation_strength, priority), never guessed.

Every adapter is defensive: a single failing/renamed upstream function degrades
to "no decisions from that source", never a 500 for the whole endpoint.
"""

from __future__ import annotations

import logging
from sqlalchemy.orm import Session

import models
from .model import Decision
from owner.settings import Settings, resolve

logger = logging.getLogger("ai.decisions")


def _assumption(setting: str, value, label: str) -> dict | None:
    """`{setting, value, label}` for a rule the owner can change (the setting's key and its value in the units the owner
    sees); None when there are no settings to read it from."""
    return None if value is None else {"setting": setting, "value": value, "label": label}


def _get(settings: Settings | None, field: str, scale: float = 1):
    value = getattr(settings, field, None) if settings is not None else None
    return None if value is None else value / scale if scale != 1 else value


MONTH_DAYS = 30


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


def from_pricing(db: Session, restaurant_id: int, settings: Settings | None = None) -> list[Decision]:
    from ai.pricing.recommendations import get_pricing_intelligence

    data = get_pricing_intelligence(db, restaurant_id, settings=settings)
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
                "kind": "loss" if rtype == "REPRICE" else "idea",
                "assumption": _assumption("margin_floor_pct", _get(settings, "margin_floor_pct"), "Lowest share you keep") if rtype == "REPRICE" else None,
            },
        ))
    out.extend(_delivery_decisions(db, restaurant_id, data.get("delivery_gaps", []), settings))
    return out


def _delivery_decisions(db: Session, restaurant_id: int, gaps: list[dict], settings: Settings | None) -> list[Decision]:
    """A dish that keeps less than the owner's floor once a delivery platform takes its commission. Worth, in a month: the
    price rise that would put it back on the floor, kept after the commission, on the plates actually sold through that platform
    in the last 30 days (none sold, nothing lost, no decision)."""
    from datetime import timedelta
    from sqlalchemy import func
    from time_utils import utcnow

    out: list[Decision] = []
    since = utcnow() - timedelta(days=30)
    for gap in gaps:
        try:
            channel = models.DeliveryChannel(gap["channel"])
        except ValueError:
            continue
        units = int(db.query(func.coalesce(func.sum(models.OrderItem.quantity), 0))
                    .join(models.Order, models.Order.id == models.OrderItem.order_id)
                    .join(models.MenuItem, models.MenuItem.id == models.OrderItem.menu_item_id)
                    .filter(models.Order.restaurant_id == restaurant_id, models.Order.delivery_channel == channel,
                            models.Order.status != models.OrderStatus.CANCELLED, models.Order.created_at >= since,
                            models.MenuItem.restaurant_id == restaurant_id, models.MenuItem.name == gap["item_name"]).scalar() or 0)
        raise_by = int(gap["recommended_delivery_price"]) - int(gap["current_price"])
        if units <= 0 or raise_by <= 0:
            continue
        platform = gap["channel"].replace("_", " ").title()
        keep = 1 - gap["commission_pct"] / 100
        out.append(Decision(
            agent="pricing_intelligence",
            category="pricing",
            action=f"Raise {gap['item_name']} on {platform} to KES {int(gap['recommended_delivery_price']) // 100:,} "
                   f"(from KES {int(gap['current_price']) // 100:,})",
            rationale=f"{platform} takes {gap['commission_pct']}%, so a {gap['item_name']} sold there keeps "
                      f"KES {int(gap['delivery_keeps_cents']) // 100:,} instead of KES {int(gap['dine_in_keeps_cents']) // 100:,} "
                      f"in the restaurant; {units} sold through {platform} in the last 30 days.",
            confidence_pct=70,
            risk=3,
            difficulty=2,
            impact_cents_month=round(raise_by * units * keep),
            data_sources=["orders by channel (30 days)", "menu_items.cost_price", "your delivery commission rates"],
            alternatives=["Keep the price and accept the lower margin", "Stop selling it through the platform"],
            entity_type="menu_item",
            meta={"channel": gap["channel"], "units_30d": units, "kind": "loss",
                  "assumption": _assumption(f"commission_{gap['channel']}_pct", _get(settings, f"commission_{gap['channel']}_pct"), f"{platform} commission")},
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


def from_supply_chain(db: Session, restaurant_id: int, settings: Settings | None = None) -> list[Decision]:
    from ai.supply_chain.intelligence import get_supply_chain_intelligence
    data = get_supply_chain_intelligence(db, restaurant_id)
    return _from_generic_recs(
        data.get("recommendations", []), "supply_chain", "supply_chain",
        default_risk=2, default_difficulty=3,
        data_sources=["purchase_orders", "suppliers.reliability_score"],
    )


def from_labor(db: Session, restaurant_id: int, settings: Settings | None = None) -> list[Decision]:
    from ai.labor.intelligence import get_labor_intelligence
    data = get_labor_intelligence(db, restaurant_id, settings=settings)
    return _from_generic_recs(
        data.get("recommendations", []), "labor_intelligence", "labor",
        default_risk=3, default_difficulty=3,
        data_sources=["labor_shifts", "orders (revenue)"],
    )


def from_menu(db: Session, restaurant_id: int, settings: Settings | None = None) -> list[Decision]:
    from ai.menu_engineer import get_menu_engineering
    data = get_menu_engineering(db, restaurant_id, settings=settings)
    return _from_generic_recs(
        data.get("recommendations", []), "menu_engineer", "menu",
        default_risk=2, default_difficulty=2,
        data_sources=["order_items", "menu_items"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Inventory — reorder / critical stock items become decisions
# ─────────────────────────────────────────────────────────────────────────────

def from_inventory(db: Session, restaurant_id: int, settings: Settings | None = None) -> list[Decision]:
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

def from_marketing(db: Session, restaurant_id: int, settings: Settings | None = None) -> list[Decision]:
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
# Signals the owner's screens already show in KES (S4.2): missing stock, a short drawer, a till price gap
# ─────────────────────────────────────────────────────────────────────────────

STOCK_WINDOW_DAYS = 7           # the same window the "Missing stock" block shows (owner/areas.py)
CASH_WINDOW_DAYS = 28           # four weeks of counts, the window "recurring patterns" looks back over


def from_stock_custody(db: Session, restaurant_id: int, settings: Settings | None = None) -> list[Decision]:
    """An ingredient the kitchen used more of than the dishes sold explain, beyond the owner's flag. Worth what the extra
    quantity cost, said as a month. Using LESS than sales explain is a counting question, not lost money — no decision."""
    from ai.stock_custody import compute_variance_report
    rows = compute_variance_report(db, restaurant_id, hours=24 * STOCK_WINDOW_DAYS, settings=settings)
    costs = {i.id: i.cost_per_unit_cents or 0
             for i in db.query(models.InventoryItem).filter(models.InventoryItem.restaurant_id == restaurant_id)}
    out: list[Decision] = []
    for r in rows:
        gap = r.actual_usage - r.theoretical_usage
        if not r.flagged or gap <= 0:
            continue
        cost = costs.get(r.inventory_item_id, 0)
        out.append(Decision(
            agent="stock_custody",
            category="custody",
            action=f"Check where the {r.item_name} went: {gap:.1f} {r.unit} more was used than your sales explain",
            rationale=f"In the last {STOCK_WINDOW_DAYS} days the kitchen used {r.actual_usage:.1f} {r.unit} of {r.item_name}; "
                      f"the dishes sold explain {r.theoretical_usage:.1f} {r.unit}. That is {r.variance_pct * 100:.0f}% more. "
                      f"A reason to check the store and the portions, not a finding about anyone.",
            confidence_pct=70,
            risk=1,
            difficulty=2,
            impact_cents_month=round(round(gap * cost) * MONTH_DAYS / STOCK_WINDOW_DAYS) if cost else None,
            data_sources=["stock movements", "recipes × dishes sold"],
            alternatives=["Count the store and the kitchen together", "Weigh a few portions"],
            entity_type="inventory_item",
            entity_id=r.inventory_item_id,
            meta={"kind": "loss", "assumption": _assumption("missing_stock_flag_pct", _get(settings, "missing_stock_flag_pct"), "Missing stock we flag")},
        ))
    return out


def from_cash_patterns(db: Session, restaurant_id: int, settings: Settings | None = None) -> list[Decision]:
    """The same weekday and shift short again and again. Worth what the shortfalls added up to over four weeks, said as a
    month. A pattern is a reason to look at that shift, never a conclusion about a person."""
    from ai.cash_reconciliation.intelligence import recurring_drawer_gaps
    out: list[Decision] = []
    for gap in recurring_drawer_gaps(db, restaurant_id, settings):
        out.append(Decision(
            agent="cash_reconciliation",
            category="cash",
            action=f"Look at {gap.when}: the cash has been short {gap.times_short} of the last {gap.of_last} times",
            rationale=f"{gap.when.capitalize()} came up short {gap.times_short} of the last {gap.of_last} times, by about "
                      f"KES {gap.average_short_cents // 100:,} each time. A repeating gap is a reason to look at how that shift "
                      f"is counted and run, not a finding about anyone.",
            confidence_pct=75,
            risk=1,
            difficulty=2,
            impact_cents_month=round(gap.total_short_cents * MONTH_DAYS / CASH_WINDOW_DAYS) or None,
            data_sources=["cash drawer counts"],
            meta={"kind": "loss", "assumption": _assumption("cash_tolerance_kes", None if settings is None else settings.cash_tolerance_cents // 100, "Cash count difference we accept")},
        ))
    return out


def from_till_price_gap(db: Session, restaurant_id: int, settings: Settings | None = None) -> list[Decision]:
    """A dish the till charged below its menu price. Worth the profit engine's own monthly figure (14 days' difference, said
    as a month). A signal to check the till — discounts, price changes, open-price items — not a finding about anyone."""
    from ai.profit.intelligence import get_profit_intelligence
    out: list[Decision] = []
    for gap in get_profit_intelligence(db, restaurant_id, settings).get("till_price_gap", []):
        out.append(Decision(
            agent="profit_intelligence",
            category="profit",
            action=f"Check the till price for {gap['item_name']}: it was charged KES {gap['avg_captured_price'] // 100:,} "
                   f"against KES {gap['menu_price'] // 100:,} on the menu",
            rationale=f"{gap['order_count']} orders in the last 14 days charged {gap['drift_pct']:g}% less than the menu price. "
                      f"Look at discounts, price changes and open-price items. A reason to check the till, not a finding about anyone.",
            confidence_pct=70,
            risk=1,
            difficulty=1,
            impact_cents_month=int(gap["estimated_monthly_leak"]) or None,
            data_sources=["orders (14 days)", "menu prices"],
            entity_type="menu_item",
            meta={"kind": "loss", "assumption": None},
        ))
    return out


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
    "custody": from_stock_custody,
    "cash": from_cash_patterns,
    "till": from_till_price_gap,
}


def collect_decisions(
    db: Session, restaurant_id: int, sources: list[str] | None = None,
    source_status: dict | None = None, settings: Settings | None = None,
) -> list[Decision]:
    """
    Gather Decisions from every (or a subset of) agent. Each source runs in
    isolation: one failing adapter never sinks the rest. The owner's settings are read once and handed to
    every adapter, so all of them judge the restaurant by the same thresholds.
    """
    settings = resolve(db, restaurant_id, settings)
    chosen = sources or list(_ADAPTERS.keys())
    decisions: list[Decision] = []
    for name in chosen:
        adapter = _ADAPTERS.get(name)
        if adapter is None:
            continue
        try:
            with db.begin_nested():
                result = adapter(db, restaurant_id, settings)
            decisions.extend(result)
            if source_status is not None:
                source_status[name] = {"state": "evaluated", "recommendations": len(result)}
        except Exception as exc:  # noqa: BLE001 — degrade per-source, never 500
            if source_status is not None:
                source_status[name] = {"state": "failed", "recommendations": None}
            logger.warning("decision adapter '%s' failed: %s", name, exc)
    return decisions
