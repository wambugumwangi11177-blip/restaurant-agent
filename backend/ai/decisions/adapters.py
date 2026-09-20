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
    from ai.pricing.recommendations import (
        get_pricing_intelligence, sync_pending_recommendations,
    )

    data = get_pricing_intelligence(db, restaurant_id)
    recommendations = data.get("recommendations", [])
    # Materialize into PENDING rows so each recommendation carries a persisted
    # id. Without it the Home card has nothing to act on — approving it could
    # only record a click, which is exactly what Approve used to do. Documented
    # safe to call on every read: it converges rather than duplicating, and
    # keeps the stored numbers in lock-step so an approval always applies the
    # price currently on screen. Guarded: a failure here degrades to advisory
    # cards, never takes down Home.
    try:
        recommendations = sync_pending_recommendations(db, restaurant_id, recommendations)
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("pricing sync failed for restaurant %s — cards will be advisory only",
                         restaurant_id)

    out: list[Decision] = []
    for rec in recommendations:
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
            recommendation_id=rec.get("id"),
            entity_type="menu_item",
            entity_id=rec.get("item_id"),
            meta={
                "type": rtype,
                "price_change_pct": rec.get("price_change_pct"),
                "when_to_apply": rec.get("when"),
                "suggested_price": suggested,
                "current_price": rec.get("current_price"),
                "item_name": rec.get("item_name"),
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
# LOSS PREVENTION — theft, variance, cash, and the data gaps that hide them
# ─────────────────────────────────────────────────────────────────────────────
#
# These four sources were built, tested and scheduled, and reached nobody: the
# only screens that displayed them are on the dashboard this owner does not
# use, and _ADAPTERS registered six sources, none of them these. A restaurant
# owner's single most expensive blind spot was computed every two hours and
# thrown away.
#
# On quantifying a loss. Ranking weights monetary impact at 0.45, so a decision
# with no figure can never outrank a priced one — an unquantified theft alert
# would sit below a KES 8,000 price tweak, which is indefensible. Where the
# module already observed real money (a drawer shortfall, an unreceipted
# payment, a variance against a costed item) that money is carried through.
# Where it did not, the decision stays unquantified rather than inventing one.
#
# On the window. These detectors run over 24 hours; impact_cents_month is a
# month. Projecting one to the other is an INFERENCE — that today's loss repeats
# — and it is labelled as one in every rationale, with the observed figure
# stated first. A restaurant KES 3,000 short each night is losing KES 90,000 a
# month if nothing changes, and that is the number that makes it outrank a price
# change. Stating only the KES 3,000 would rank the theft last.

LOSS_WINDOW_HOURS = 24


def _project_monthly(observed_cents: int, window_hours: int = LOSS_WINDOW_HOURS) -> int | None:
    """Observed loss over a window → monthly run-rate. None for nothing observed.

    Deliberately simple and deliberately visible: the rationale always states
    the observed figure and the fact that the monthly number assumes the pattern
    continues. Silent extrapolation is how a model starts lying.
    """
    if not observed_cents or observed_cents <= 0:
        return None
    return int(observed_cents * (24 / max(window_hours, 1)) * 30)


def from_stock_custody(db: Session, restaurant_id: int) -> list[Decision]:
    """Items whose actual usage diverges from what the recipes say it should be.

    The gap between theoretical and actual usage is the industry-standard
    shrinkage signal (directive 016). Above 3% it is worth a question; below it
    is portioning noise.
    """
    from ai import stock_custody
    import models

    out: list[Decision] = []
    flagged = stock_custody.flagged_items(db, restaurant_id, hours=LOSS_WINDOW_HOURS)
    if not flagged:
        return out

    costs = {
        row.id: (row.cost_per_unit_cents or 0)
        for row in db.query(models.InventoryItem).filter(
            models.InventoryItem.restaurant_id == restaurant_id).all()
    }

    for v in flagged:
        excess_units = max(v.actual_usage - v.theoretical_usage, 0.0)
        unit_cost = costs.get(v.inventory_item_id, 0)
        # An item with no cost entered gets no figure rather than a zero loss —
        # the same rule as ai/profit/intelligence.py. A zero here would rank a
        # real theft at the bottom of the list.
        observed = int(excess_units * unit_cost) if (unit_cost and excess_units) else 0
        monthly = _project_monthly(observed)

        pct = round((v.variance_pct or 0) * 100, 1)
        rationale = (
            f"Recipes account for {v.theoretical_usage:.1f} {v.unit}; "
            f"{v.actual_usage:.1f} {v.unit} actually left stock in the last "
            f"{LOSS_WINDOW_HOURS}h — a {pct}% gap against a {stock_custody.VARIANCE_THRESHOLD * 100:.0f}% threshold."
        )
        if observed:
            rationale += (
                f" The excess is worth KES {observed // 100:,} at this item's cost price"
                f"; KES {monthly // 100:,}/month if it keeps happening."
            )
        else:
            rationale += " No cost price on this item, so the shilling value cannot be stated."

        out.append(Decision(
            agent="stock_custody",
            category="loss_prevention",
            action=f"Check {v.item_name} usage against the recipes",
            rationale=rationale,
            # The threshold is met or it is not — this is a measurement, not a
            # forecast, so confidence is high and does not vary with size.
            confidence_pct=85,
            risk=2,        # asking a question; the risk is a needless one
            difficulty=2,  # a stock count and a conversation
            impact_cents_month=monthly,
            data_sources=["stock_movements", "menu_ingredients", "orders"],
            entity_type="inventory_item",
            entity_id=v.inventory_item_id,
            alternatives=["Recount the item before acting",
                          "Check for an unrecorded transfer or waste entry"],
            meta={"variance_pct": pct, "window_hours": LOSS_WINDOW_HOURS,
                  "observed_loss_cents": observed or None},
        ))
    return out


def from_fraud(db: Session, restaurant_id: int) -> list[Decision]:
    """Register-level patterns the stock side cannot see: voids, refunds,
    payments marked paid without a receipt, and edits outside trading hours."""
    from ai.fraud import detection

    report = detection.compute_fraud_report(db, restaurant_id, window_hours=LOSS_WINDOW_HOURS)
    out: list[Decision] = []

    for spike in report.void_spikes:
        out.append(Decision(
            agent="fraud_detection",
            category="loss_prevention",
            action=f"Review {spike.actor_email}'s cancellations",
            rationale=(
                f"{spike.window_count} cancellation(s) in the last {LOSS_WINDOW_HOURS}h "
                f"against their own average of {spike.baseline_mean:.1f} "
                f"(± {spike.baseline_stddev:.1f}). Measured against this person's "
                f"own history, not a shop-wide number."
            ),
            confidence_pct=75,
            # Naming a person is the risk here. A wrong accusation costs more
            # than the voids, which is why this is a review, not an action.
            risk=3,
            difficulty=2,
            impact_cents_month=None,
            data_sources=["order_audits"],
            entity_type="user",
            entity_id=spike.actor_user_id,
            alternatives=["Check whether a shift or system issue explains the run",
                          "Watch one more window before raising it"],
            meta={"window_count": spike.window_count,
                  "baseline_mean": spike.baseline_mean},
        ))

    for burst in report.refund_velocity:
        out.append(Decision(
            agent="fraud_detection",
            category="loss_prevention",
            action=f"Ask {burst.actor_email} about {burst.count} refunds in {burst.window_minutes} minutes",
            rationale=(
                f"{burst.count} cancellations or refunds inside {burst.window_minutes} "
                f"minutes by one person. A slow elevated rate and a burst are different "
                f"signals; this is the burst."
            ),
            confidence_pct=80,
            risk=3,
            difficulty=1,
            impact_cents_month=None,
            data_sources=["order_audits"],
            entity_type="user",
            entity_id=burst.actor_user_id,
            alternatives=["Check whether one table was re-rung several times"],
            meta={"order_ids": burst.order_ids[:10], "count": burst.count},
        ))

    if report.payment_mismatches:
        # This one IS money: each order was marked paid with nothing from
        # Safaricom to settle against.
        observed = sum(f.total_cents or 0 for f in report.payment_mismatches)
        monthly = _project_monthly(observed)
        out.append(Decision(
            agent="fraud_detection",
            category="loss_prevention",
            action=f"Chase {len(report.payment_mismatches)} M-Pesa order(s) with no receipt",
            rationale=(
                f"{len(report.payment_mismatches)} order(s) worth KES {observed // 100:,} "
                f"are marked paid by M-Pesa with no Safaricom receipt on file — a manual "
                f"override, not a settled payment. KES {(monthly or 0) // 100:,}/month at "
                f"this rate."
            ),
            confidence_pct=90,
            risk=1,        # checking a receipt accuses nobody
            difficulty=1,
            impact_cents_month=monthly,
            data_sources=["orders", "mpesa_callbacks"],
            alternatives=["Reconcile against the M-Pesa statement first"],
            meta={"order_ids": [f.order_id for f in report.payment_mismatches][:10],
                  "observed_cents": observed},
        ))

    if report.off_hours:
        low, high = report.off_hours[0].normal_hour_range
        out.append(Decision(
            agent="fraud_detection",
            category="loss_prevention",
            action=f"Review {len(report.off_hours)} order change(s) made outside trading hours",
            rationale=(
                f"{len(report.off_hours)} order status change(s) outside the "
                f"{low:02d}:00–{high:02d}:00 window your own order history says is normal. "
                f"The window is derived from your trading pattern, not configured."
            ),
            confidence_pct=65,
            risk=2,
            difficulty=2,
            impact_cents_month=None,
            data_sources=["order_audits"],
            alternatives=["Check whether a late close or a private event explains it"],
            meta={"order_ids": [f.order_id for f in report.off_hours][:10],
                  "normal_hour_range": [low, high]},
        ))
    return out


def from_cash_reconciliation(db: Session, restaurant_id: int) -> list[Decision]:
    """Drawer counts that do not match what the orders say should be there."""
    from ai.cash_reconciliation import intelligence

    report = intelligence.compute_reconciliation_report(
        db, restaurant_id, window_hours=LOSS_WINDOW_HOURS)
    flagged = [v for v in report.drawer_variances if v.flagged]
    if not flagged:
        return []

    # Shortfalls and overages are both errors, but only a shortfall is money
    # gone. They are reported together and quantified on the shortfall.
    short = sum(-v.variance_cents for v in flagged if v.variance_cents < 0)
    over = sum(v.variance_cents for v in flagged if v.variance_cents > 0)
    monthly = _project_monthly(short)

    parts = []
    if short:
        parts.append(f"KES {short // 100:,} short")
    if over:
        parts.append(f"KES {over // 100:,} over")
    rationale = (
        f"{len(flagged)} drawer count(s) outside tolerance in the last "
        f"{LOSS_WINDOW_HOURS}h: {' and '.join(parts)}. Tolerance is the greater of "
        f"KES {intelligence.DRAWER_TOLERANCE_CENTS // 100:,} or "
        f"{intelligence.DRAWER_TOLERANCE_PCT * 100:.0f}% of expected."
    )
    if monthly:
        rationale += f" KES {monthly // 100:,}/month if the shortfall repeats."

    return [Decision(
        agent="cash_reconciliation",
        category="loss_prevention",
        action=f"Reconcile {len(flagged)} cash drawer count(s)",
        rationale=rationale,
        confidence_pct=88,
        risk=1,
        difficulty=2,
        impact_cents_month=monthly,
        data_sources=["cash_drawer_counts", "orders"],
        alternatives=["Recount before the next service",
                      "Check for an unrecorded float movement"],
        meta={"count_ids": [v.count_id for v in flagged][:10],
              "short_cents": short, "over_cents": over},
    )]


def from_data_quality(db: Session, restaurant_id: int) -> list[Decision]:
    """Cost prices missing or implausible — the gap that makes every profit
    figure a partial one, and hides the worst leaks from leak detection."""
    from ai.data_quality import get_cost_price_quality

    data = get_cost_price_quality(db, restaurant_id)
    summary = data.get("summary") or {}
    missing = summary.get("missing_cost_count") or 0
    high = summary.get("high_severity_count") or 0
    if not missing and not high:
        return []

    coverage = summary.get("coverage_pct", 0)
    issues = data.get("issues") or []
    names = ", ".join(i.get("item_name", "?") for i in issues[:3])

    if missing:
        action = f"Add cost prices to {missing} dish(es)"
        rationale = (
            f"{missing} dish(es) have no cost price, so they are left out of every "
            f"margin and leak calculation ({names}). Cost data covers {coverage}% "
            f"of your menu — an item with no cost can never be flagged as losing money."
        )
    else:
        action = f"Check {high} cost price(s) that look wrong"
        rationale = (
            f"{high} dish(es) have a cost price that looks like a data-entry slip "
            f"({names}) — a decimal in the wrong place skews the profit figures "
            f"they feed."
        )

    return [Decision(
        agent="data_quality",
        category="loss_prevention",
        action=action,
        rationale=rationale,
        # A missing field is a fact, not a prediction.
        confidence_pct=95,
        risk=1,
        difficulty=2,
        impact_cents_month=None,
        data_sources=["menu_items", "order_items"],
        alternatives=["Start with the items that sell most"],
        meta={"missing_cost_count": missing, "high_severity_count": high,
              "coverage_pct": coverage},
    )]


# ─────────────────────────────────────────────────────────────────────────────
# Aggregator
# ─────────────────────────────────────────────────────────────────────────────

# Registering a source here is what makes it visible to the owner. For most of
# this system's life the list held these six and nothing else, so fraud
# detection, stock variance, cash reconciliation and cost-data quality ran on
# schedule, passed their tests, and reached no screen the owner opens.
#
# Loss prevention is listed first deliberately. Ranking decides the order the
# owner reads, so position here does not change anything — but the order says
# what this system is for, and money already gone outranks money not yet made.
_ADAPTERS = {
    # Loss prevention — what is leaving, that should not be.
    "fraud": from_fraud,
    "stock_custody": from_stock_custody,
    "cash_reconciliation": from_cash_reconciliation,
    "data_quality": from_data_quality,
    # Optimisation — what could be better.
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
